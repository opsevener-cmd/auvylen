"""The global spend cap holds under concurrent requests with real PostgreSQL row locks."""

import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from aevyra_api.accounts import AccountService
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.photo_check.gemini import Assessment, ModelPhoto, Usage
from aevyra_api.photo_check.models import PhotoCheckAnalysis, PhotoCheckBudgetDay
from aevyra_api.photo_check.service import PhotoCheckService
from aevyra_contracts.photo_check import CONSENT_VERSION, PhotoCheckConsentRequest
from pydantic import SecretStr
from sqlalchemy import func, select
from test_postgres_commercial import postgres_services

pytestmark = pytest.mark.integration
# Dummy key in the current "AQ." format (dotted, 53 characters). Never a real key.
TEST_KEY = "AQ.Ab8RN6-test-only-dummy-key-not-real.0123456789abcd"


class SlowProvider:
    model = "fake-model"

    def max_output_tokens(self, photos: int) -> int:
        return 300 + 450 * photos

    def estimated_input_tokens(self, photos: int) -> int:
        return 1400 + 700 * photos

    def assess(self, images, language, roast="off"):
        time.sleep(0.2)  # Keep reservations in flight concurrently.
        photo = ModelPhoto(
            index=0,
            refusal_reason=None,
            lighting=7,
            sharpness=7,
            framing=7,
            expression=7,
            eye_contact=7,
            background=7,
            tips=[],
            band=3,
        )
        return Assessment([photo], Usage(1600, 400))


def test_concurrent_checks_never_exceed_the_daily_budget():
    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test",
            free_hook_enabled=True,
            gemini_api_key=SecretStr(TEST_KEY),
            free_hook_paid_tier_confirmed=True,
            photo_check_free_signup=100,
            # The pause threshold is a full-size advanced reservation (26475 micro-USD).
            free_hook_daily_budget_usd=Decimal("0.06"),
            _env_file=None,
        )
        service = PhotoCheckService(sessions, settings, lambda s, choice: SlowProvider())
        users = []
        for index in range(3):
            user, _ = AccountService(sessions, settings).register(
                f"photo-cap-{index}", "test-photo-cap-password"
            )
            service.accept_consent(
                user.id,
                PhotoCheckConsentRequest(
                    consent_version=CONSENT_VERSION, adult_confirmed=True, processing_accepted=True
                ),
            )
            users.append(user.id)

        def attempt(index: int) -> str:
            try:
                service.analyze(users[index % 3], [b"photo"], "en")
                return "ok"
            except DomainError as error:
                return error.detail

        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(attempt, range(24)))
        assert set(outcomes) <= {"ok", "photo_check_paused"}
        assert "photo_check_paused" in outcomes
        with sessions() as session:
            budget = session.scalars(select(PhotoCheckBudgetDay)).one()
            completed = session.scalar(
                select(func.count())
                .select_from(PhotoCheckAnalysis)
                .where(PhotoCheckAnalysis.status == "COMPLETED")
            )
        # Every reservation was released, and real spend stayed within the cap.
        assert budget.reserved_micro_usd == 0
        assert budget.spent_micro_usd <= 60_000
        assert completed == outcomes.count("ok")


def test_concurrent_checks_never_grant_extra_free_checks_or_overspend_credits():
    from aevyra_api.credits.ledger import append_credit, lock_wallet
    from aevyra_api.credits.models import CreditTransaction, Wallet

    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test",
            free_hook_enabled=True,
            gemini_api_key=SecretStr(TEST_KEY),
            free_hook_paid_tier_confirmed=True,
            free_hook_daily_budget_usd=Decimal("100"),
            photo_check_free_signup=2,
            photo_check_free_weekly=1,
            photo_check_credit_cost=1,
            _env_file=None,
        )
        service = PhotoCheckService(sessions, settings, lambda s, choice: SlowProvider())
        user, _ = AccountService(sessions, settings).register(
            "photo-quota-race", "test-photo-cap-password"
        )
        service.accept_consent(
            user.id,
            PhotoCheckConsentRequest(
                consent_version=CONSENT_VERSION, adult_confirmed=True, processing_accepted=True
            ),
        )
        with sessions.begin() as session:
            append_credit(
                session,
                lock_wallet(session, user.id),
                amount=2,
                kind="TEST_GRANT",
                reference_type="test",
                reference_id="grant",
                key="test-grant",
            )

        def attempt(_: int) -> str:
            try:
                return service.analyze(user.id, [b"photo"], "en").funding
            except DomainError as error:
                return error.detail

        with ThreadPoolExecutor(max_workers=10) as pool:
            outcomes = list(pool.map(attempt, range(10)))
        # Exactly 2 signup + 1 weekly free checks, then 2 paid ones; the rest are refused.
        assert sorted(outcomes) == sorted(
            ["free_signup"] * 2
            + ["free_weekly"]
            + ["credits"] * 2
            + ["photo_check_insufficient_credits"] * 5
        )
        with sessions() as session:
            balance = session.scalar(select(Wallet.cached_balance).where(Wallet.user_id == user.id))
            debits = session.scalar(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.transaction_type == "PHOTO_CHECK")
            )
        assert balance == 0 and debits == 2
