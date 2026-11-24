"""Free photo-quality check: consent, per-user limit, global spend cap, ranked result.

Spend is tracked in integer micro-USD. Each call first reserves a worst-case cost under a
row lock on the day's budget row, so concurrent requests cannot exceed the cap. The
provider is called outside any transaction, then the real cost from the response's token
counts replaces the reservation.
"""

import logging
import math
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from uuid import UUID

from aevyra_contracts import EngineMetadata
from aevyra_contracts.photo_check import (
    CONSENT_VERSION,
    CRITERIA,
    MAX_PHOTOS,
    Availability,
    Language,
    PhotoCheckConsentRequest,
    PhotoCheckPhoto,
    PhotoCheckResult,
    PhotoCheckStatus,
    PhotoScores,
)
from aevyra_inference.engine import EnginePolicyError, EngineRegistry
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.photo_check.gemini import (
    ENGINE,
    ESTIMATOR,
    MAX_TIP_CHARS,
    PROMPT_VERSION,
    GeminiPhotoQuality,
    ModelPhoto,
    PhotoQualityProvider,
    ProviderError,
    TokenBudget,
    Usage,
    api_key_problem,
)
from aevyra_api.photo_check.models import (
    PhotoCheckAnalysis,
    PhotoCheckBudgetDay,
    PhotoCheckConsent,
)
from aevyra_api.preferences.images import decode_image_bytes

logger = logging.getLogger("aevyra.photo_check")
_reported_key_problems: set[str] = set()
RESULT_RETENTION = timedelta(days=30)
STALE_RESERVATION = timedelta(minutes=10)
PROVIDER_LONG_EDGE = 1024
ProviderFactory = Callable[[Settings], PhotoQualityProvider]


def gemini_provider(settings: Settings) -> PhotoQualityProvider:
    assert settings.gemini_api_key is not None
    return GeminiPhotoQuality(
        settings.gemini_api_key.get_secret_value(),
        settings.free_hook_model,
        thinking_level=settings.free_hook_thinking_level,
        timeout=float(settings.free_hook_timeout_seconds),
    )


def micro_usd(tokens: int, price_per_million: Decimal) -> int:
    """USD per 1M tokens times tokens is micro-USD; round up so spend is never understated."""
    return math.ceil(Decimal(tokens) * price_per_million)


def prepare_photo(payload: bytes) -> bytes:
    """Bounded decode (existing upload limits), metadata stripped, 1024 px JPEG for the call."""
    decoded = decode_image_bytes(payload)
    with Image.open(BytesIO(decoded.image)) as image:
        image.thumbnail((PROVIDER_LONG_EDGE, PROVIDER_LONG_EDGE))
        output = BytesIO()
        image.save(output, format="JPEG", quality=85)
    return output.getvalue()


def ranked_photos(photos: Sequence[ModelPhoto]) -> list[PhotoCheckPhoto]:
    views = []
    for photo in photos:
        if photo.refusal_reason is not None:
            views.append(
                PhotoCheckPhoto(
                    index=photo.index,
                    rank=None,
                    usable=False,
                    refusal_reason=photo.refusal_reason,
                    scores=None,
                    raw_score=None,
                    display_score=None,
                    tips=[],
                )
            )
            continue
        scores = PhotoScores.model_validate({name: getattr(photo, name) for name in CRITERIA})
        # The model's own overall opinion is not trusted: the score is the plain mean.
        raw = sum(getattr(scores, name) for name in CRITERIA) / len(CRITERIA)
        tips = [tip.strip()[:MAX_TIP_CHARS] for tip in photo.tips if tip.strip()][:2]
        views.append(
            PhotoCheckPhoto(
                index=photo.index,
                rank=None,
                usable=True,
                refusal_reason=None,
                scores=scores,
                raw_score=raw,
                display_score=round(raw, 1),
                tips=tips,
            )
        )
    usable = sorted(
        (view for view in views if view.usable), key=lambda v: (-(v.raw_score or 0), v.index)
    )
    for rank, view in enumerate(usable, start=1):
        view.rank = rank
    return views


class PhotoCheckService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        provider_factory: ProviderFactory = gemini_provider,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.provider_factory = provider_factory

    # Availability and policy -------------------------------------------------------------

    def metadata(self) -> EngineMetadata:
        s = self.settings
        return EngineMetadata(
            slug=ENGINE,
            display_name="Gemini photo-quality check",
            version=f"{s.free_hook_model}/{PROMPT_VERSION}",
            licensing_status=(
                "Gemini API Standard paid tier under the Gemini API Additional Terms; "
                "paid-tier prompts and responses are not used to improve Google products"
            ),
            provenance="Third-party hosted VLM; photos supplied and consented by the user",
            # Evidence: the operator confirms paid-tier billing (FREE_HOOK_PAID_TIER_CONFIRMED).
            commercial_allowed=s.free_hook_paid_tier_confirmed,
            research_allowed=False,
            production_enabled=s.free_hook_enabled and s.gemini_api_key is not None,
            synthetic=False,
        )

    def configuration(self) -> Availability:
        s = self.settings
        if not s.free_hook_enabled:
            return "disabled"
        if s.gemini_api_key is None:
            return "not_configured"
        problem = api_key_problem(s.gemini_api_key.get_secret_value())
        if problem is not None:
            # Tell the operator once per process; never log the key or any part of it.
            if problem not in _reported_key_problems:
                _reported_key_problems.add(problem)
                logger.error("photo_check_api_key_invalid", extra={"error_type": problem})
            return "not_configured"
        if not s.free_hook_paid_tier_confirmed:
            return "paid_tier_unconfirmed"
        try:
            EngineRegistry.check_policy(
                self.metadata(), production=s.api_environment == "production"
            )
        except EnginePolicyError:
            return "paid_tier_unconfirmed"
        return "ready"

    def budget_micro_usd(self) -> int:
        return micro_usd(1_000_000, self.settings.free_hook_daily_budget_usd)

    def reservation(self, provider: TokenBudget, photos: int) -> int:
        s = self.settings
        return micro_usd(
            provider.estimated_input_tokens(photos), s.free_hook_price_input_per_m
        ) + micro_usd(provider.max_output_tokens(photos), s.free_hook_price_output_per_m)

    def worst_case_reservation(self) -> int:
        # Pause before the budget cannot cover a full-size request.
        return self.reservation(ESTIMATOR, MAX_PHOTOS)

    @staticmethod
    def today() -> date:
        return now().date()

    def used_today(self, session: Session, user: UUID, day: date) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(PhotoCheckAnalysis)
                .where(
                    PhotoCheckAnalysis.user_id == user,
                    PhotoCheckAnalysis.day == day,
                    PhotoCheckAnalysis.status.in_(("RESERVED", "COMPLETED")),
                )
            )
            or 0
        )

    def consented(self, session: Session, user: UUID) -> bool:
        return (
            session.scalar(
                select(PhotoCheckConsent.id).where(
                    PhotoCheckConsent.user_id == user,
                    PhotoCheckConsent.consent_version == CONSENT_VERSION,
                )
            )
            is not None
        )

    def paused(self, session: Session, day: date) -> bool:
        row = session.get(PhotoCheckBudgetDay, day)
        committed = (row.spent_micro_usd + row.reserved_micro_usd) if row else 0
        return committed + self.worst_case_reservation() > self.budget_micro_usd()

    def status(self, user: UUID) -> PhotoCheckStatus:
        reason = self.configuration()
        day = self.today()
        with self.sessions() as session:
            if reason == "ready" and self.paused(session, day):
                reason = "paused"
            return PhotoCheckStatus(
                available=reason == "ready",
                reason=reason,
                consent_version=CONSENT_VERSION,
                consent_required=not self.consented(session, user),
                used_today=self.used_today(session, user, day),
                daily_limit=self.settings.free_hook_user_daily_limit,
                max_photos=MAX_PHOTOS,
            )

    def accept_consent(self, user: UUID, body: PhotoCheckConsentRequest) -> None:
        try:
            with self.sessions.begin() as session:
                if self.consented(session, user):
                    return
                session.add(
                    PhotoCheckConsent(
                        user_id=user,
                        consent_version=body.consent_version,
                        adult_confirmed=body.adult_confirmed,
                        processing_accepted=body.processing_accepted,
                    )
                )
        except IntegrityError:
            return  # A concurrent request recorded the same consent.

    def check_submit(self, user: UUID) -> None:
        """Cheap checks before any photo is decoded."""
        if self.configuration() != "ready":
            raise DomainError("photo_check_unavailable", 503)
        with self.sessions() as session:
            if not self.consented(session, user):
                raise DomainError("photo_check_consent_required", 403)

    # Reserve, call, settle ---------------------------------------------------------------

    def _budget_row(self, session: Session, day: date) -> PhotoCheckBudgetDay:
        if session.get(PhotoCheckBudgetDay, day) is None:
            try:
                with session.begin_nested():
                    session.add(PhotoCheckBudgetDay(day=day))
            except IntegrityError:
                pass  # Created concurrently; lock the existing row below.
        row = session.scalar(
            select(PhotoCheckBudgetDay)
            .where(PhotoCheckBudgetDay.day == day)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert row is not None
        return row

    def _sweep(self, session: Session) -> None:
        """Abandoned reservations (process died mid-call) count as spent; old results go."""
        stale = session.scalars(
            select(PhotoCheckAnalysis)
            .where(
                PhotoCheckAnalysis.status == "RESERVED",
                PhotoCheckAnalysis.created_at < now() - STALE_RESERVATION,
            )
            .with_for_update()
        ).all()
        for row in stale:
            budget = self._budget_row(session, row.day)
            budget.reserved_micro_usd = max(0, budget.reserved_micro_usd - row.reserved_micro_usd)
            budget.spent_micro_usd += row.reserved_micro_usd
            row.status, row.failure_reason = "FAILED", "abandoned"
            row.cost_micro_usd, row.completed_at = row.reserved_micro_usd, now()
        session.execute(
            update(PhotoCheckAnalysis)
            .where(
                PhotoCheckAnalysis.created_at < now() - RESULT_RETENTION,
                PhotoCheckAnalysis.result.is_not(None),
            )
            .values(result=None)
            # Pure SQL; no in-memory objects depend on cleared results.
            .execution_options(synchronize_session=False)
        )

    def _reserve(
        self, user: UUID, provider: PhotoQualityProvider, photos: int, language: Language
    ) -> tuple[UUID, int, date]:
        amount = self.reservation(provider, photos)
        day = self.today()
        analysis_id: UUID | None = None
        with self.sessions.begin() as session:
            budget = self._budget_row(session, day)
            self._sweep(session)
            if not self.consented(session, user):
                raise DomainError("photo_check_consent_required", 403)
            if self.used_today(session, user, day) >= self.settings.free_hook_user_daily_limit:
                raise DomainError("photo_check_daily_limit", 429)
            committed = budget.spent_micro_usd + budget.reserved_micro_usd
            # Same rule as status(): pause once a full-size request no longer fits.
            if committed + max(amount, self.worst_case_reservation()) > self.budget_micro_usd():
                if budget.paused_at is None:
                    budget.paused_at = now()
                    logger.warning("photo_check_paused")
                # The pause marker commits; the request itself is refused below.
            else:
                budget.reserved_micro_usd += amount
                row = PhotoCheckAnalysis(
                    user_id=user,
                    day=day,
                    status="RESERVED",
                    photo_count=photos,
                    language=language,
                    model=provider.model,
                    prompt_version=PROMPT_VERSION,
                    consent_version=CONSENT_VERSION,
                    reserved_micro_usd=amount,
                )
                session.add(row)
                session.flush()
                analysis_id = row.id
        if analysis_id is None:
            raise DomainError("photo_check_paused", 503)
        return analysis_id, amount, day

    def _settle(
        self,
        analysis_id: UUID,
        day: date,
        usage: Usage | None,
        result: dict[str, object] | None,
        failure: str | None,
    ) -> None:
        s = self.settings
        cost = (
            micro_usd(usage.input_tokens, s.free_hook_price_input_per_m)
            + micro_usd(usage.output_tokens, s.free_hook_price_output_per_m)
            if usage
            else 0
        )
        with self.sessions.begin() as session:
            budget = self._budget_row(session, day)
            row = session.get(PhotoCheckAnalysis, analysis_id, with_for_update=True)
            assert row is not None
            if row.status == "RESERVED":
                budget.reserved_micro_usd = max(
                    0, budget.reserved_micro_usd - row.reserved_micro_usd
                )
                budget.spent_micro_usd += cost
            else:  # Swept as abandoned and charged the reservation; correct to the real cost.
                budget.spent_micro_usd = max(
                    0, budget.spent_micro_usd - (row.cost_micro_usd or 0) + cost
                )
            row.status = "FAILED" if failure else "COMPLETED"
            row.failure_reason = failure
            row.cost_micro_usd = cost
            row.input_tokens = usage.input_tokens if usage else None
            row.output_tokens = usage.output_tokens if usage else None
            row.result = result
            row.completed_at = now()

    def analyze(self, user: UUID, images: Sequence[bytes], language: Language) -> PhotoCheckResult:
        if not 1 <= len(images) <= MAX_PHOTOS:
            raise DomainError("photo_check_invalid_photos", 422)
        if self.configuration() != "ready":
            raise DomainError("photo_check_unavailable", 503)
        provider = self.provider_factory(self.settings)
        analysis_id, _, day = self._reserve(user, provider, len(images), language)
        try:
            assessment = provider.assess(images, language)
        except ProviderError as error:
            self._settle(analysis_id, day, error.usage, None, error.reason)
            logger.error(
                "photo_check_provider_failed",
                extra={
                    "analysis_id": str(analysis_id),
                    "error_type": error.reason,
                    "status_code": error.status_code,
                },
            )
            if error.reason == "blocked":
                raise DomainError("photo_check_blocked", 422) from None
            raise DomainError("photo_check_provider_failed", 503) from None
        except Exception as error:
            self._settle(analysis_id, day, None, None, "internal_error")
            logger.error(
                "photo_check_internal_error",
                extra={"analysis_id": str(analysis_id), "error_type": type(error).__name__},
            )
            raise
        photos = ranked_photos(assessment.photos)
        created = now()
        result: dict[str, object] = {"photos": [photo.model_dump(mode="json") for photo in photos]}
        self._settle(analysis_id, day, assessment.usage, result, None)
        logger.info("photo_check_completed", extra={"analysis_id": str(analysis_id)})
        with self.sessions() as session:
            used = self.used_today(session, user, day)
        return PhotoCheckResult(
            id=analysis_id,
            photos=photos,
            engine=ENGINE,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            created_at=created,
            used_today=used,
            daily_limit=self.settings.free_hook_user_daily_limit,
        )
