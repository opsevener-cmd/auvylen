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
        return 200 + 220 * photos

    def estimated_input_tokens(self, photos: int) -> int:
        return 900 + 700 * photos

    def assess(self, images, language):
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
        )
        return Assessment([photo], Usage(1600, 400))


def test_concurrent_checks_never_exceed_the_daily_budget():
    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test",
            free_hook_enabled=True,
            gemini_api_key=SecretStr(TEST_KEY),
            free_hook_paid_tier_confirmed=True,
            free_hook_user_daily_limit=100,
            # Room for about four full-size reservations (4570 micro-USD each).
            free_hook_daily_budget_usd=Decimal("0.02"),
            _env_file=None,
        )
        service = PhotoCheckService(sessions, settings, lambda s: SlowProvider())
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
        assert budget.spent_micro_usd <= 20_000
        assert completed == outcomes.count("ok")
