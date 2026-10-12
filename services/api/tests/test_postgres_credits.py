from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from aevyra_api.accounts import AccountService, RedisRateLimiter, pepper
from aevyra_api.commercial.models import Analysis, AnalysisResult
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.codes import generate_batch, redeem
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import CreditTransaction, Redemption, Wallet
from aevyra_api.database import DependencyChecks
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.mock import MockScoringEngine
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_postgres_commercial import postgres_services

pytestmark = pytest.mark.integration


def setup_credit(sessions, amount=1):
    settings = Settings(api_environment="test", _env_file=None)
    user, _ = AccountService(sessions, settings).register("concurrency-pilot", "test-long-password")
    with sessions.begin() as session:
        wallet = lock_wallet(session, user.id)
        append_credit(
            session,
            wallet,
            amount=amount,
            kind="PROMOTION",
            reference_type="test",
            reference_id="initial",
            key="initial",
        )
    return user


def test_postgres_same_code_different_users_exactly_one_winner(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with postgres_services() as (sessions, *_):
        settings = Settings(api_environment="test", _env_file=None)
        users = [
            AccountService(sessions, settings).register(f"redeemer-{i}", "test-long-password")[0]
            for i in range(8)
        ]
        generate_batch(
            sessions,
            pepper(settings),
            name="Concurrent",
            channel="arbitrary_channel",
            sku="ten-credit",
            credits=10,
            quantity=1,
            output=Path("exports/race.csv"),
        )
        import csv

        with Path("exports/race.csv").open(newline="", encoding="utf-8") as file:
            code = next(csv.DictReader(file))["code"]

        def attempt(user):
            try:
                return redeem(sessions, pepper(settings), user.id, code)
            except DomainError as error:
                assert error.status_code == 400
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(attempt, users))
        assert sum(response is not None for response in responses) == 1
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(Redemption)) == 1
            assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 1
            assert session.scalar(select(func.sum(Wallet.cached_balance))) == 10
            assert session.scalar(select(func.sum(CreditTransaction.amount))) == 10


@pytest.mark.parametrize("same_key", [False, True])
def test_postgres_analysis_concurrency_cannot_overspend(same_key):
    with postgres_services() as (sessions, *_):
        user = setup_credit(sessions)
        calls = []

        class CountingMock(MockScoringEngine):
            def predict(self, prepared: bytes) -> float:
                calls.append(prepared)
                return super().predict(prepared)

        service = CreditAnalysisService(
            sessions, EngineRegistry([CountingMock()]), production=False
        )
        key = str(uuid4())
        keys = [key] * 8 if same_key else [str(uuid4()) for _ in range(8)]

        def attempt(request_key):
            try:
                return service.create(user.id, "aevyra-test-analysis", request_key)
            except DomainError as error:
                assert error.detail == "Insufficient Credits"
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(attempt, keys))
        assert sum(response is not None for response in responses) == (8 if same_key else 1)
        assert len(calls) == 1
        with sessions() as session:
            assert session.scalar(select(Wallet.cached_balance)) == 0
            assert session.scalar(select(func.sum(CreditTransaction.amount))) == 0
            for model in (Analysis, AnalysisResult):
                assert session.scalar(select(func.count()).select_from(model)) == 1
            assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 2


def test_postgres_concurrent_refund_and_immutable_history():
    with postgres_services() as (sessions, *_):
        user = setup_credit(sessions)

        class Failure(MockScoringEngine):
            def predict(self, prepared: bytes) -> float:
                raise RuntimeError("secret should not be logged")

        service = CreditAnalysisService(sessions, EngineRegistry([Failure()]), production=False)
        analysis_id = service.create(user.id, "aevyra-test-analysis", str(uuid4()))
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(service.refund_failed, [analysis_id] * 8))
        with sessions() as session:
            assert session.scalar(select(Wallet.cached_balance)) == 1
            assert session.scalar(select(func.sum(CreditTransaction.amount))) == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(CreditTransaction)
                    .where(CreditTransaction.transaction_type == "ANALYSIS_REFUND")
                )
                == 1
            )
            assert session.scalar(select(Analysis.status)) == "FAILED"
        for sql in (
            "UPDATE credit_transactions SET amount=99",
            "DELETE FROM credit_transactions",
            "TRUNCATE credit_transactions CASCADE",
        ):
            with pytest.raises(DBAPIError), sessions.begin() as session:
                session.execute(text(sql))


def test_real_redis_rate_limiter():
    checks = DependencyChecks(Settings())
    key = "integration:" + uuid4().hex
    try:
        limiter = RedisRateLimiter(checks.redis)
        limiter.check(key, 2, 30)
        limiter.check(key, 2, 30)
        with pytest.raises(DomainError) as error:
            limiter.check(key, 2, 30)
        assert error.value.status_code == 429
    finally:
        checks.redis.delete("auvylen:rate:" + key)
        checks.close()
