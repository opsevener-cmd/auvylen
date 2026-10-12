import csv
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from aevyra_api.accounts import COOKIE, HASHER, RedisRateLimiter, pepper
from aevyra_api.commercial.models import Analysis, Product, now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.codes import INVALID, digest_code, generate_batch, generate_code, redeem
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import (
    AccountSession,
    CreditTransaction,
    Redemption,
    RedemptionBatch,
    RedemptionCode,
    User,
    Wallet,
)
from aevyra_inference.engine import EngineRegistry
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import func, select

PASSWORD = "test-only-long-account-password"
ORIGIN = {"Origin": "http://localhost:3000"}


class TestLimiter:
    __test__ = False

    def __init__(self):
        self.counts = {}

    def check(self, key, limit, seconds):
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] > limit:
            raise DomainError("Too many attempts", 429)


@pytest.fixture
def credits(commerce, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    commerce.client.app.state.rate_limiter = TestLimiter()
    commerce.client.app.state.credit_registry = EngineRegistry([commerce.engine])
    return commerce


def csrf_headers(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return {**ORIGIN, "X-CSRF-Token": response.json()["csrf_token"]}


def register(client, identifier="pilot@example.test"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "login_identifier": identifier,
            "password": PASSWORD,
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def user_id(credits):
    with credits.sessions() as session:
        return session.scalar(select(User.id))


def make_batch(credits, quantity=1, amount=10):
    batch_id = generate_batch(
        credits.sessions,
        pepper(credits.client.app.state.settings),
        name="Pilot",
        channel="any_future_channel",
        sku="pilot-10",
        credits=amount,
        quantity=quantity,
        output=Path("exports/pilot.csv"),
    )
    with Path("exports/pilot.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    return batch_id, rows


def grant(credits, amount=10):
    with credits.sessions.begin() as session:
        wallet = lock_wallet(session, user_id(credits))
        return append_credit(
            session,
            wallet,
            amount=amount,
            kind="PROMOTION",
            reference_type="test",
            reference_id="fixture",
            key=str(uuid4()),
        ).id


def run_analysis(credits, key=None, **extra):
    return credits.client.post(
        "/api/v1/credit-analyses",
        json={
            "product_slug": "aevyra-test-analysis",
            "idempotency_key": key or str(uuid4()),
            **extra,
        },
        headers=csrf_headers(credits.client),
    )


def test_register_login_logout_hash_and_cookie(credits):
    client = credits.client
    assert client.get("/api/v1/account").status_code == 401
    user = register(client, "Pilot@Example.Test")
    assert user["public_user_id"].startswith("usr_")
    assert user["login_identifier"] == "pilot@example.test"
    assert client.get("/api/v1/account").json()["wallet"] == {"balance": 0, "transactions": []}
    with credits.sessions() as session:
        stored = session.scalar(select(User))
        assert stored.password_hash.startswith("$argon2id$")
        assert HASHER.verify(stored.password_hash, PASSWORD)
        assert PASSWORD not in stored.password_hash
        token = client.cookies.get(COOKIE)
        assert session.scalar(select(AccountSession.token_digest)) != token
    assert (
        client.post("/api/v1/auth/logout", json={}, headers=csrf_headers(client)).status_code == 200
    )
    assert client.get("/api/v1/account").status_code == 401
    response = client.post(
        "/api/v1/auth/login",
        json={
            "login_identifier": "pilot@example.test",
            "password": PASSWORD,
        },
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"


def test_incorrect_password_unknown_user_disabled_and_expiry(credits):
    client = credits.client
    register(client)
    for identifier in ("pilot@example.test", "unknown@example.test"):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "login_identifier": identifier,
                "password": "incorrect-long-password",
            },
            headers=csrf_headers(client),
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid login credentials"
    with credits.sessions.begin() as session:
        session.scalar(select(AccountSession)).expires_at = now() - timedelta(seconds=1)
    assert client.get("/api/v1/account").status_code == 401
    with credits.sessions.begin() as session:
        session.scalar(select(User)).disabled_at = now()
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "login_identifier": "pilot@example.test",
                "password": PASSWORD,
            },
            headers=csrf_headers(client),
        ).status_code
        == 401
    )


def test_csrf_and_validation_do_not_echo_secrets(credits):
    client = credits.client
    body = {"login_identifier": "pilot@example.test", "password": PASSWORD}
    assert client.post("/api/v1/auth/register", json=body).status_code == 403
    headers = csrf_headers(client)
    assert (
        client.post(
            "/api/v1/auth/register",
            json=body,
            headers={
                **headers,
                "Origin": "https://untrusted.example",
            },
        ).status_code
        == 403
    )
    response = client.post(
        "/api/v1/auth/register", json={**body, "user_id": "attacker"}, headers=headers
    )
    assert response.status_code == 422
    assert PASSWORD not in response.text
    register(client)
    secret = "SECRET" * 20
    response = client.post("/api/v1/redeem", json={"code": secret}, headers=csrf_headers(client))
    assert response.status_code == 422 and secret not in response.text


def test_redeem_and_analysis_complete_local_flow(credits):
    register(credits.client)
    batch, rows = make_batch(credits)
    response = credits.client.post(
        "/api/v1/redeem",
        json={"code": rows[0]["code"].lower()},
        headers=csrf_headers(credits.client),
    )
    assert response.json() == {"credits_added": 10, "balance": 10}
    analysis = run_analysis(credits)
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "COMPLETED"
    result = credits.client.get(f"/api/v1/credit-analyses/{analysis.json()['id']}/result")
    assert result.json()["metadata"]["synthetic"] is True
    account = credits.client.get("/api/v1/account").json()
    assert account["wallet"]["balance"] == 9
    assert sorted(t["amount"] for t in account["wallet"]["transactions"]) == [-1, 10]
    assert credits.engine.calls == 1
    with credits.sessions() as session:
        redemption = session.scalar(select(Redemption))
        assert redemption.source_metadata == {
            "batch": batch,
            "channel": "any_future_channel",
            "sku": "pilot-10",
        }


@pytest.mark.parametrize("failure", ["invalid", "expired", "disabled", "used", "malformed"])
def test_redemption_generic_failures(credits, failure):
    register(credits.client)
    _, rows = make_batch(credits)
    code = rows[0]["code"]
    with credits.sessions.begin() as session:
        batch = session.scalar(select(RedemptionBatch))
        if failure == "expired":
            batch.expires_at = now() - timedelta(seconds=1)
        if failure == "disabled":
            batch.active = False
    if failure == "used":
        redeem(credits.sessions, pepper(credits.client.app.state.settings), user_id(credits), code)
    elif failure == "invalid":
        code = generate_code()
    elif failure == "malformed":
        code = "AUV-invalid"
    response = credits.client.post(
        "/api/v1/redeem", json={"code": code}, headers=csrf_headers(credits.client)
    )
    assert response.status_code == 400
    assert response.json()["detail"] == INVALID
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(CreditTransaction)) == (
            1 if failure == "used" else 0
        )


def test_generation_quantity_hmac_no_plaintext_and_export_guard(credits):
    _, rows = make_batch(credits, quantity=25)
    assert len(rows) == 25 and len({row["code"] for row in rows}) == 25
    assert rows[0]["credits"] == "10"
    with credits.sessions() as session:
        codes = list(session.scalars(select(RedemptionCode)))
        assert len(codes) == 25
        digest = digest_code(rows[0]["code"], pepper(credits.client.app.state.settings))
        assert digest in {code.lookup_digest for code in codes}
        for code in codes:
            assert len(code.lookup_digest) == 64 and len(code.masked_suffix) == 4
            assert all(row["code"] not in str(code.__dict__) for row in rows)
    with patch("aevyra_api.credits.codes.secrets.choice", return_value="K") as choice:
        generated = generate_code()
        assert choice.call_count == 24 and generated.startswith("AUV-")
    with pytest.raises(DomainError, match="Export"):
        generate_batch(
            credits.sessions,
            "test" * 10,
            name="Pilot",
            channel="manual",
            sku="pilot",
            credits=10,
            quantity=1,
            output=Path("unsafe.csv"),
        )
    root = Path(__file__).resolve().parents[3]
    assert "exports/" in (root / ".gitignore").read_text()


def test_wallet_ledger_balance_limits_and_idempotency(credits):
    register(credits.client)
    grant(credits, 3)
    with credits.sessions.begin() as session:
        wallet = lock_wallet(session, user_id(credits))
        args = dict(
            amount=-2, kind="TEST_DEBIT", reference_type="test", reference_id="x", key="once"
        )
        first = append_credit(session, wallet, **args)
        assert append_credit(session, wallet, **args).id == first.id
        assert wallet.cached_balance == 1
        with pytest.raises(DomainError, match="Insufficient"):
            append_credit(session, wallet, **{**args, "amount": -2, "key": "twice"})
    with credits.sessions() as session:
        assert session.scalar(select(func.sum(CreditTransaction.amount))) == 1
        assert session.scalar(select(Wallet.cached_balance)) == 1


def test_insufficient_and_price_override_rejected(credits):
    register(credits.client)
    assert run_analysis(credits).status_code == 409
    grant(credits)
    assert run_analysis(credits, credit_cost=0).status_code == 422
    with credits.sessions.begin() as session:
        session.scalar(select(Product)).credit_cost = 3
    assert run_analysis(credits).status_code == 200
    assert credits.client.get("/api/v1/account").json()["wallet"]["balance"] == 7


def test_duplicate_analysis_and_exactly_once_failure_refund(credits):
    register(credits.client)
    grant(credits)
    key = str(uuid4())
    first = run_analysis(credits, key)
    assert run_analysis(credits, key).json()["id"] == first.json()["id"]
    assert credits.engine.calls == 1
    credits.engine.fail = True
    failed = run_analysis(credits).json()
    assert failed["status"] == "FAILED"
    service = CreditAnalysisService(
        credits.sessions, EngineRegistry([credits.engine]), production=False
    )
    from uuid import UUID

    for _ in range(3):
        service.refund_failed(UUID(failed["id"]))
    with credits.sessions() as session:
        assert session.scalar(select(Wallet.cached_balance)) == 9
        assert (
            session.scalar(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.transaction_type == "ANALYSIS_REFUND")
            )
            == 1
        )


def test_cross_account_authorization_and_legacy_path_denial(credits):
    client = credits.client
    register(client)
    grant(credits)
    analysis_id = run_analysis(credits).json()["id"]
    assert client.get(f"/api/v1/analyses/{analysis_id}").status_code == 404
    assert client.get(f"/api/v1/analyses/{analysis_id}/result").status_code == 404
    client.post("/api/v1/auth/logout", json={}, headers=csrf_headers(client))
    register(client, "another@example.test")
    assert client.get("/api/v1/account").json()["wallet"]["balance"] == 0
    assert client.get(f"/api/v1/credit-analyses/{analysis_id}").status_code == 404
    assert client.get(f"/api/v1/credit-analyses/{analysis_id}/result").status_code == 404
    assert client.get(f"/api/v1/wallets/{user_id(credits)}").status_code == 404
    assert (
        client.post(
            "/api/v1/redeem",
            json={"code": generate_code(), "user_id": str(user_id(credits))},
            headers=csrf_headers(client),
        ).status_code
        == 422
    )


def test_rate_limits_and_redis_fail_closed(credits):
    register(credits.client)
    for _ in range(10):
        assert (
            credits.client.post(
                "/api/v1/redeem",
                json={"code": generate_code()},
                headers=csrf_headers(credits.client),
            ).status_code
            == 400
        )
    assert (
        credits.client.post(
            "/api/v1/redeem", json={"code": generate_code()}, headers=csrf_headers(credits.client)
        ).status_code
        == 429
    )
    with patch("redis.Redis.eval", side_effect=RedisConnectionError):
        from redis import Redis

        with pytest.raises(DomainError) as error:
            RedisRateLimiter(Redis()).check("unit", 10, 300)
        assert error.value.status_code == 503


def test_pepper_required_and_https_cookie_configuration(monkeypatch):
    monkeypatch.delenv("REDEMPTION_CODE_PEPPER", raising=False)
    with pytest.raises(ValueError, match="PEPPER"):
        Settings(_env_file=None)
    assert pepper(Settings(api_environment="test", _env_file=None))
    with pytest.raises(ValueError, match="PEPPER"):
        Settings(redemption_code_pepper="REPLACE_PLACEHOLDER_SECRET_12345678", _env_file=None)


def test_login_bruteforce_and_secure_cookie(credits):
    client = credits.client
    headers = csrf_headers(client)
    client.app.state.settings.session_cookie_secure = True
    response = client.post(
        "/api/v1/auth/register",
        json={
            "login_identifier": "secure-pilot",
            "password": PASSWORD,
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    client.app.state.settings.session_cookie_secure = False
    client.cookies.clear()
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "login_identifier": "secure-pilot",
                "password": "wrong-long-password",
            },
            headers=csrf_headers(client),
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "login_identifier": "secure-pilot",
                "password": PASSWORD,
            },
            headers=csrf_headers(client),
        ).status_code
        == 429
    )


def test_duplicate_register_and_current_session_disabled(credits):
    register(credits.client)
    response = credits.client.post(
        "/api/v1/auth/register",
        json={
            "login_identifier": "pilot@example.test",
            "password": PASSWORD,
        },
        headers=csrf_headers(credits.client),
    )
    assert response.status_code == 409
    with credits.sessions.begin() as session:
        session.scalar(select(User)).disabled_at = now()
    assert credits.client.get("/api/v1/account").status_code == 401


def test_production_credit_analysis_fails_before_deduction(credits):
    register(credits.client)
    grant(credits)
    credits.client.app.state.settings.api_environment = "production"
    assert run_analysis(credits).status_code == 404
    with credits.sessions() as session:
        assert session.scalar(select(Wallet.cached_balance)) == 10
        assert session.scalar(select(func.count()).select_from(Analysis)) == 0
