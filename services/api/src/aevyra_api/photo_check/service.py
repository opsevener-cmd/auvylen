"""Photo check: consent, free quota then Credits, global spend cap, ranked result with
photo technique, constructive appearance feedback, an AI impression band and an optional
photo-only roast (AGENTS.md, owner decision 2026-11-25).

Quota: PHOTO_CHECK_FREE_SIGNUP lifetime free checks, then PHOTO_CHECK_FREE_WEEKLY per ISO
week (Monday 00:00 UTC), then PHOTO_CHECK_CREDIT_COST Credits. Free checks count only when
they are reserved or completed, so a failed check never uses one. Credits are debited when
the check is reserved and refunded with a compensating ledger entry if it fails, so the net
charge applies only to a successful result and concurrent requests cannot overspend.

Spend is tracked in integer micro-USD. Each call first reserves a worst-case cost under a
row lock on the day's budget row, so concurrent requests cannot exceed the cap. The
provider is called outside any transaction, then the real cost from the response's token
counts replaces the reservation.
"""

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Literal
from uuid import UUID, uuid4

from aevyra_contracts import EngineMetadata
from aevyra_contracts.photo_check import (
    CONSENT_VERSION,
    CRITERIA,
    MAX_PHOTOS,
    QUALITY_GATE,
    Availability,
    Funding,
    Language,
    PhotoAppearance,
    PhotoCheckConsentRequest,
    PhotoCheckPhoto,
    PhotoCheckResult,
    PhotoCheckStatus,
    PhotoRoast,
    PhotoScores,
    RefusalReason,
    RoastLevel,
)
from aevyra_inference.engine import EnginePolicyError, EngineRegistry
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import User, Wallet
from aevyra_api.entitlements import is_owner
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
from aevyra_api.photo_check.safety import appearance_lines, roast_lines
from aevyra_api.preferences.images import decode_image_bytes

logger = logging.getLogger("aevyra.photo_check")
_reported_key_problems: set[str] = set()
RESULT_RETENTION = timedelta(days=30)
STALE_RESERVATION = timedelta(minutes=10)
PROVIDER_LONG_EDGE = 1024
Tier = Literal["default", "advanced"]


@dataclass(frozen=True)
class ModelChoice:
    """Which Gemini model serves a check, with its prices (USD per 1M tokens)."""

    tier: Tier
    model: str
    price_input_per_m: Decimal
    price_output_per_m: Decimal
    thinking_level: str


def tier_for(funding: Funding) -> Tier:
    # Free checks use the default model; checks paid with Credits and the Owner's use the
    # advanced one (owner decision 2026-11-27).
    return "advanced" if funding in ("credits", "owner") else "default"


def model_choice(settings: Settings, tier: Tier) -> ModelChoice:
    if tier == "advanced":
        return ModelChoice(
            "advanced",
            settings.gemini_model_advanced,
            settings.gemini_advanced_price_input_per_m,
            settings.gemini_advanced_price_output_per_m,
            settings.gemini_advanced_thinking_level,
        )
    return ModelChoice(
        "default",
        settings.gemini_model,
        settings.free_hook_price_input_per_m,
        settings.free_hook_price_output_per_m,
        settings.free_hook_thinking_level,
    )


def cost_micro_usd(usage: Usage, choice: ModelChoice) -> int:
    return micro_usd(usage.input_tokens, choice.price_input_per_m) + micro_usd(
        usage.output_tokens, choice.price_output_per_m
    )


ProviderFactory = Callable[[Settings, ModelChoice], PhotoQualityProvider]
# Model refusals are reported neutrally: one message for more than one person, a possible
# minor or explicit content, so the reason is never spelled out to the user.
PUBLIC_REFUSAL: dict[str, RefusalReason] = {
    "no_person": "no_person",
    "not_a_photo": "not_a_photo",
    "multiple_people": "cannot_analyse",
    "appears_under_18": "cannot_analyse",
    "explicit": "cannot_analyse",
}
ACTIVE = ("RESERVED", "COMPLETED")


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def gemini_provider(settings: Settings, choice: ModelChoice) -> PhotoQualityProvider:
    assert settings.gemini_api_key is not None
    return GeminiPhotoQuality(
        settings.gemini_api_key.get_secret_value(),
        choice.model,
        thinking_level=choice.thinking_level,
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


def passes_quality_gate(raw_score: float | None) -> bool:
    """Stage 1 gate: stage 2 (appearance, AI impression, roast) needs a good enough photo."""
    return raw_score is not None and raw_score >= QUALITY_GATE


def ranked_photos(photos: Sequence[ModelPhoto], roast: RoastLevel = "off") -> list[PhotoCheckPhoto]:
    views = []
    for photo in photos:
        if photo.refusal_reason is not None:
            views.append(
                PhotoCheckPhoto(
                    index=photo.index,
                    rank=None,
                    usable=False,
                    refusal_reason=PUBLIC_REFUSAL[photo.refusal_reason],
                    scores=None,
                    raw_score=None,
                    display_score=None,
                    tips=[],
                    quality_passed=False,
                )
            )
            continue
        scores = PhotoScores.model_validate({name: getattr(photo, name) for name in CRITERIA})
        # The model's own overall opinion is not trusted: the score is the plain mean.
        raw = sum(getattr(scores, name) for name in CRITERIA) / len(CRITERIA)
        tips = [tip.strip()[:MAX_TIP_CHARS] for tip in photo.tips if tip.strip()][:2]
        assert photo.band is not None  # ModelPhoto guarantees a band for usable photos.
        passed = passes_quality_gate(raw)
        # Below the gate, the appearance, band and roast from the same call are discarded
        # here: they are never returned or stored.
        appearance = (
            PhotoAppearance(
                strengths=appearance_lines(photo.appearance_strengths),
                flattering=appearance_lines(photo.appearance_flattering),
                tips=appearance_lines(photo.appearance_tips),
                band=photo.band,  # type: ignore[arg-type]  # Validated 1-4 by ModelPhoto.
            )
            if passed
            else None
        )
        joke = (
            None
            if roast == "off" or not passed
            else PhotoRoast(lines=roast_lines(photo.roast_lines), vibe=photo.vibe)  # type: ignore[arg-type]  # Validated against ARCHETYPES.
        )
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
                quality_passed=passed,
                appearance=appearance,
                roast=joke,
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
            display_name="Gemini photo check (technique and appearance)",
            version=f"{s.gemini_model}+{s.gemini_model_advanced}/{PROMPT_VERSION}",
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

    def reservation(self, provider: TokenBudget, photos: int, choice: ModelChoice) -> int:
        return micro_usd(
            provider.estimated_input_tokens(photos), choice.price_input_per_m
        ) + micro_usd(provider.max_output_tokens(photos), choice.price_output_per_m)

    def worst_case_reservation(self) -> int:
        # Pause before the budget cannot cover a full-size request on the dearest model.
        return max(
            self.reservation(ESTIMATOR, MAX_PHOTOS, model_choice(self.settings, tier))
            for tier in ("default", "advanced")
        )

    @staticmethod
    def today() -> date:
        return now().date()

    def _active(self, session: Session, user: UUID, *conditions: object) -> int:
        return int(
            session.scalar(
                select(func.count())
                .select_from(PhotoCheckAnalysis)
                .where(
                    PhotoCheckAnalysis.user_id == user,
                    PhotoCheckAnalysis.status.in_(ACTIVE),
                    *conditions,  # type: ignore[arg-type]
                )
            )
            or 0
        )

    def free_remaining(self, session: Session, user: UUID, day: date) -> tuple[int, int]:
        """(signup checks left, weekly checks left this ISO week)."""
        s = self.settings
        signup = self._active(session, user, PhotoCheckAnalysis.funding == "free_signup")
        weekly = self._active(
            session,
            user,
            PhotoCheckAnalysis.funding == "free_weekly",
            PhotoCheckAnalysis.day >= week_start(day),
        )
        return max(0, s.photo_check_free_signup - signup), max(
            0, s.photo_check_free_weekly - weekly
        )

    def next_free_on(self, signup: int, weekly: int, day: date) -> date | None:
        if signup or weekly or not self.settings.photo_check_free_weekly:
            return None
        return week_start(day) + timedelta(days=7)

    def roast_available(self, session: Session, user: UUID) -> bool:
        # The first check stays friendly: roast mode unlocks after one completed check.
        return (
            session.scalar(
                select(PhotoCheckAnalysis.id)
                .where(PhotoCheckAnalysis.user_id == user, PhotoCheckAnalysis.status == "COMPLETED")
                .limit(1)
            )
            is not None
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
            signup, weekly = self.free_remaining(session, user, day)
            account = session.get(User, user)
            owner = is_owner(account)
            wallet = session.scalar(select(Wallet).where(Wallet.user_id == user))
            return PhotoCheckStatus(
                available=reason == "ready",
                reason=reason,
                consent_version=CONSENT_VERSION,
                consent_required=not self.consented(session, user),
                free_checks_now=signup + weekly,
                free_signup_remaining=signup,
                next_free_on=None if owner else self.next_free_on(signup, weekly, day),
                credit_cost=0 if owner else self.settings.photo_check_credit_cost,
                credit_balance=wallet.cached_balance if wallet else 0,
                roast_available=self.roast_available(session, user),
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
            self._refund(session, row)
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

    def _refund(self, session: Session, row: PhotoCheckAnalysis) -> None:
        """Compensating entry for a check that produced no result. Idempotent by key."""
        if row.funding != "credits" or not row.credits_charged:
            return
        append_credit(
            session,
            lock_wallet(session, row.user_id),
            amount=row.credits_charged,
            kind="PHOTO_CHECK_REFUND",
            reference_type="photo_check",
            reference_id=str(row.id),
            key=f"photo-check-refund:{row.id}",
        )

    def _funding(self, session: Session, user: UUID, day: date) -> Funding:
        if is_owner(session.get(User, user)):
            return "owner"
        signup, weekly = self.free_remaining(session, user, day)
        if signup:
            return "free_signup"
        if weekly:
            return "free_weekly"
        return "credits"

    def record_spend(self, usage: Usage, choice: ModelChoice) -> int:
        """Add spend made outside a user check (the consistency script) to today's budget."""
        cost = cost_micro_usd(usage, choice)
        with self.sessions.begin() as session:
            self._budget_row(session, self.today()).spent_micro_usd += cost
        return cost

    def _reserve(
        self,
        user: UUID,
        photos: int,
        language: Language,
        roast: RoastLevel,
    ) -> tuple[UUID, date, Funding, int, RoastLevel, ModelChoice]:
        day = self.today()
        analysis_id: UUID | None = None
        with self.sessions.begin() as session:
            budget = self._budget_row(session, day)
            self._sweep(session)
            if not self.consented(session, user):
                raise DomainError("photo_check_consent_required", 403)
            if roast != "off" and not self.roast_available(session, user):
                roast = "off"  # The first check stays friendly.
            funding = self._funding(session, user, day)
            # The model follows the funding, and the reservation uses that model's prices.
            choice = model_choice(self.settings, tier_for(funding))
            amount = self.reservation(ESTIMATOR, photos, choice)
            cost = self.settings.photo_check_credit_cost if funding == "credits" else 0
            if cost:
                wallet = lock_wallet(session, user)
                if wallet.cached_balance < cost:
                    raise DomainError("photo_check_insufficient_credits", 409)
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
                    id=uuid4(),
                    user_id=user,
                    day=day,
                    status="RESERVED",
                    photo_count=photos,
                    language=language,
                    model=choice.model,
                    prompt_version=PROMPT_VERSION,
                    consent_version=CONSENT_VERSION,
                    reserved_micro_usd=amount,
                    funding=funding,
                    credits_charged=cost,
                    roast=roast,
                )
                session.add(row)
                session.flush()
                if cost:
                    # Debit now, refund on failure: the net charge applies only to a result.
                    append_credit(
                        session,
                        wallet,
                        amount=-cost,
                        kind="PHOTO_CHECK",
                        reference_type="photo_check",
                        reference_id=str(row.id),
                        key=f"photo-check:{row.id}",
                    )
                analysis_id = row.id
        if analysis_id is None:
            raise DomainError("photo_check_paused", 503)
        return analysis_id, day, funding, cost, roast, choice

    def _settle(
        self,
        analysis_id: UUID,
        day: date,
        usage: Usage | None,
        result: dict[str, object] | None,
        failure: str | None,
        choice: ModelChoice,
    ) -> None:
        cost = cost_micro_usd(usage, choice) if usage else 0
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
            if failure and row.status == "RESERVED":
                self._refund(session, row)
            row.status = "FAILED" if failure else "COMPLETED"
            row.failure_reason = failure
            row.cost_micro_usd = cost
            row.input_tokens = usage.input_tokens if usage else None
            row.output_tokens = usage.output_tokens if usage else None
            row.result = result
            row.completed_at = now()

    def analyze(
        self,
        user: UUID,
        images: Sequence[bytes],
        language: Language,
        roast: RoastLevel = "off",
    ) -> PhotoCheckResult:
        if not 1 <= len(images) <= MAX_PHOTOS:
            raise DomainError("photo_check_invalid_photos", 422)
        if self.configuration() != "ready":
            raise DomainError("photo_check_unavailable", 503)
        analysis_id, day, funding, cost, roast, choice = self._reserve(
            user, len(images), language, roast
        )
        try:
            provider = self.provider_factory(self.settings, choice)
            assessment = provider.assess(images, language, roast)
        except ProviderError as error:
            self._settle(analysis_id, day, error.usage, None, error.reason, choice)
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
            self._settle(analysis_id, day, None, None, "internal_error", choice)
            logger.error(
                "photo_check_internal_error",
                extra={"analysis_id": str(analysis_id), "error_type": type(error).__name__},
            )
            raise
        photos = ranked_photos(assessment.photos, roast)
        created = now()
        result: dict[str, object] = {"photos": [photo.model_dump(mode="json") for photo in photos]}
        self._settle(analysis_id, day, assessment.usage, result, None, choice)
        logger.info("photo_check_completed", extra={"analysis_id": str(analysis_id)})
        with self.sessions() as session:
            signup, weekly = self.free_remaining(session, user, day)
        return PhotoCheckResult(
            id=analysis_id,
            photos=photos,
            engine=ENGINE,
            model=choice.model,
            advanced=choice.tier == "advanced",
            prompt_version=PROMPT_VERSION,
            created_at=created,
            funding=funding,
            credits_charged=cost,
            free_checks_now=signup + weekly,
            next_free_on=None if funding == "owner" else self.next_free_on(signup, weekly, day),
        )
