"""Product entitlement policy. Never replaces provider, privacy or resource gates."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User

OWNER_LOGIN = "owner_god"


def is_owner(user: User | None) -> bool:
    return bool(user and user.role == "owner" and user.disabled_at is None)


def require_owner(user: User | None) -> None:
    if not is_owner(user):
        raise DomainError("Owner authorization required", 403)


def product_access(user: User, *, standard_allowed: bool) -> bool:
    """New features supply ordinary entitlement; Owner gets permitted products by default.

    Callers must independently verify implementation/licensing/availability and ownership.
    This function cannot authorize administrative operations.
    """
    return user.disabled_at is None and (is_owner(user) or standard_allowed)


def credit_cost(user: User, configured_cost: int) -> int:
    return 0 if is_owner(user) else configured_cost


@dataclass(frozen=True)
class ResearchLimits:
    projects: int = 20
    datasets: int = 100
    images: int = 500
    storage_bytes: int = 512 * 1024 * 1024
    pairs: int = 10000
    models: int = 100
    pending: int = 2
    daily: int = 50


def research_limits(session: Session, user_id: UUID, settings: Settings) -> ResearchLimits:
    if is_owner(session.get(User, user_id)):
        return ResearchLimits(
            projects=settings.owner_max_projects,
            datasets=settings.owner_max_datasets,
            images=settings.owner_max_images,
            storage_bytes=settings.owner_storage_mib * 1024 * 1024,
            pairs=settings.owner_max_pairs,
            models=settings.owner_max_models,
            pending=settings.owner_max_pending,
            daily=settings.owner_daily_limit,
        )
    return ResearchLimits(
        pending=settings.research_max_pending, daily=settings.research_daily_limit
    )
