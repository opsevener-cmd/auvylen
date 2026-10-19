"""Owner-only administration. No endpoint reads another user's private artifacts."""

import os
import resource
import shutil
from dataclasses import asdict
from typing import Annotated

from aevyra_contracts.owner import (
    AdminCommand,
    AdminPage,
    AdminResult,
    BatchCreateCommand,
    CreditGrantCommand,
    OwnerOverview,
    ResearchAccessCommand,
    UserStatusCommand,
)
from aevyra_inference.extractors import MOBILENET, availability
from aevyra_inference.preference import EXTRACTOR
from aevyra_inference.providers import ProviderCatalog
from fastapi import APIRouter, Depends, Query, Request
from pydantic import JsonValue
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.sql.elements import ColumnElement

from aevyra_api.accounts import COOKIE, pepper
from aevyra_api.admin_models import AdminAudit, FreeAnalysisGrant
from aevyra_api.administration import Administration
from aevyra_api.commercial.models import now
from aevyra_api.credits.models import (
    CreditTransaction,
    RedemptionBatch,
    RedemptionCode,
    User,
    Wallet,
)
from aevyra_api.entitlements import require_owner, research_limits
from aevyra_api.preferences.models import PreferenceDataset, PreferenceImage
from aevyra_api.preferences.training_models import CustomModel
from aevyra_api.research.models import ResearchAccess, ResearchJob
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions

router = APIRouter(prefix="/api/v1/owner", tags=["Owner administration"])


def owner_user(request: Request, user: CurrentUser) -> User:
    request.state.admin_actor_id = user.id
    rate(request, "owner", 120, user.public_user_id)
    require_owner(user)
    return user


Owner = Annotated[User, Depends(owner_user)]
Page = Annotated[int, Query(ge=1, le=100000)]
Size = Annotated[int, Query(ge=1, le=100)]


@router.get("/overview", response_model=OwnerOverview)
def overview(request: Request, user: Owner) -> OwnerOverview:
    settings = config(request)
    with sessions(request)() as session:

        def count(model: type, *conditions: ColumnElement[bool]) -> int:
            return int(
                session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0
            )

        counts = {
            "users": count(User),
            "active_users": count(User, User.disabled_at.is_(None)),
            "disabled_users": count(User, User.disabled_at.is_not(None)),
            "research_grants": count(ResearchAccess, ResearchAccess.enabled.is_(True)),
            "datasets": count(PreferenceDataset, PreferenceDataset.deleted_at.is_(None)),
            "images": count(PreferenceImage, PreferenceImage.deleted_at.is_(None)),
            "models": count(CustomModel, CustomModel.state != "DELETED"),
        }
        jobs = {
            str(status): int(total)
            for status, total in session.execute(
                select(ResearchJob.status, func.count()).group_by(ResearchJob.status)
            )
        }
        credits = {
            "ledger_entries": count(CreditTransaction),
            "net_credits": int(
                session.scalar(select(func.coalesce(func.sum(CreditTransaction.amount), 0))) or 0
            ),
            "free_owner_analyses": count(FreeAnalysisGrant),
        }
        for kind, amount in session.execute(
            select(CreditTransaction.transaction_type, func.sum(CreditTransaction.amount)).group_by(
                CreditTransaction.transaction_type
            )
        ):
            credits[kind.lower() + "_total"] = int(amount)
        usage: list[dict[str, JsonValue]] = [
            {"provider": provider, "kind": kind, "status": state, "jobs": int(total)}
            for provider, kind, state, total in session.execute(
                select(
                    ResearchJob.provider, ResearchJob.kind, ResearchJob.status, func.count()
                ).group_by(ResearchJob.provider, ResearchJob.kind, ResearchJob.status)
            )
        ]
        active_leases = count(
            ResearchJob, ResearchJob.status == "RUNNING", ResearchJob.lease_until > now()
        )
        quotas = asdict(research_limits(session, user.id, settings))
    health: dict[str, JsonValue] = {
        "database": "ok",
        "active_worker_leases": active_leases,
        "worker": "unknown",
        "api_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "host_load_1m": os.getloadavg()[0],
    }
    try:
        cache = request.app.state.checks.redis
        cache.ping()
        health["redis"] = "ok"
        heartbeat = cache.get("auvylen:worker:heartbeat:" + settings.worker_queue)
        health["worker"] = (
            "recent heartbeat"
            if heartbeat
            else ("active job lease" if active_leases else "no recent heartbeat")
        )
    except RedisError:
        health["redis"] = "unavailable"
    for label, path in (
        ("uploads", settings.private_upload_root),
        ("models", settings.private_model_root),
    ):
        try:
            disk_usage = shutil.disk_usage(path)
            health[f"{label}_filesystem_free_bytes"] = disk_usage.free
            health[f"{label}_filesystem_total_bytes"] = disk_usage.total
        except OSError:
            health[f"{label}_filesystem_free_bytes"] = None
    quotas["running_jobs_global"] = settings.research_max_running
    quotas["rated_images_per_training"] = 500
    return OwnerOverview(
        counts=counts,
        jobs=jobs,
        credits=credits,
        health=health,
        providers=[
            asdict(p)
            for p in ProviderCatalog(
                settings.enabled_model_providers, settings.private_model_root
            ).statuses()
        ],
        extractors=[
            {
                "id": name,
                "available": available,
                "reason": reason,
            }
            for name in (EXTRACTOR, MOBILENET)
            for available, reason in [
                availability(name, settings.private_model_root / "pretrained")
            ]
        ],
        usage=usage,
        quotas=quotas,
        environment=settings.api_environment,
        research_enabled=settings.research_mode,
    )


@router.get("/users", response_model=AdminPage)
def users(
    request: Request,
    user: Owner,
    page: Page = 1,
    page_size: Size = 25,
    search: Annotated[str, Query(max_length=120)] = "",
    status: Annotated[str, Query(pattern="^(all|active|disabled)$")] = "all",
) -> AdminPage:
    with sessions(request)() as session:
        query = (
            select(User, Wallet.cached_balance, ResearchAccess.enabled)
            .join(Wallet)
            .outerjoin(ResearchAccess)
        )
        if search:
            query = query.where(User.login_identifier.contains(search.lower(), autoescape=True))
        if status != "all":
            query = query.where(
                User.disabled_at.is_(None) if status == "active" else User.disabled_at.is_not(None)
            )
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items: list[dict[str, JsonValue]] = [
            {
                "public_user_id": row.public_user_id,
                "login_identifier": row.login_identifier,
                "role": row.role,
                "disabled": row.disabled_at is not None,
                "balance": balance,
                "research_enabled": bool(granted or row.role == "owner"),
                "created_at": row.created_at.isoformat(),
            }
            for row, balance, granted in session.execute(
                query.order_by(User.created_at, User.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ]
        return AdminPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/users/{public_id}/credits", response_model=AdminResult)
def ledger(
    public_id: str, request: Request, user: Owner, page: Page = 1, page_size: Size = 25
) -> AdminResult:
    with sessions(request)() as session:
        target = session.scalar(select(User).where(User.public_user_id == public_id))
        if target is None:
            from aevyra_api.commercial.state import DomainError

            raise DomainError("User not found", 404)
        wallet = session.scalar(select(Wallet).where(Wallet.user_id == target.id))
        assert wallet is not None
        query = select(CreditTransaction).where(CreditTransaction.wallet_id == wallet.id)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        derived = int(
            session.scalar(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                    CreditTransaction.wallet_id == wallet.id
                )
            )
            or 0
        )
        entries: list[JsonValue] = [
            {
                "id": str(e.id),
                "amount": e.amount,
                "transaction_type": e.transaction_type,
                "reference_type": e.reference_type,
                "reference_id": e.reference_id,
                "balance_after": e.balance_after,
                "created_at": e.created_at.isoformat(),
            }
            for e in session.scalars(
                query.order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ]
        return AdminResult(
            data={
                "public_user_id": public_id,
                "cached_balance": wallet.cached_balance,
                "ledger_balance": derived,
                "reconciled": derived == wallet.cached_balance,
                "total": total,
                "page": page,
                "page_size": page_size,
                "entries": entries,
            }
        )


def service(request: Request) -> Administration:
    return Administration(sessions(request), config(request))


@router.post("/users/{public_id}/status", response_model=AdminResult, dependencies=[Depends(csrf)])
def set_status(
    public_id: str, body: UserStatusCommand, request: Request, user: Owner
) -> AdminResult:
    admin = service(request)
    return AdminResult(
        data=admin.mutate(
            user.id,
            request.cookies[COOKIE],
            "user.status",
            public_id,
            body,
            lambda s: admin.user_status(s, public_id, body),
        )
    )


@router.post(
    "/users/{public_id}/research", response_model=AdminResult, dependencies=[Depends(csrf)]
)
def set_research(
    public_id: str, body: ResearchAccessCommand, request: Request, user: Owner
) -> AdminResult:
    admin = service(request)
    return AdminResult(
        data=admin.mutate(
            user.id,
            request.cookies[COOKIE],
            "user.research",
            public_id,
            body,
            lambda s: admin.research_access(s, public_id, body),
        )
    )


@router.post("/users/{public_id}/credits", response_model=AdminResult, dependencies=[Depends(csrf)])
def grant_credits(
    public_id: str, body: CreditGrantCommand, request: Request, user: Owner
) -> AdminResult:
    admin = service(request)
    return AdminResult(
        data=admin.mutate(
            user.id,
            request.cookies[COOKIE],
            "credits.grant",
            public_id,
            body,
            lambda s: admin.grant(s, user.id, public_id, body),
        )
    )


@router.get("/batches", response_model=AdminPage)
def batches(request: Request, user: Owner, page: Page = 1, page_size: Size = 25) -> AdminPage:
    with sessions(request)() as session:
        total = session.scalar(select(func.count()).select_from(RedemptionBatch)) or 0
        items: list[dict[str, JsonValue]] = []
        for b in session.scalars(
            select(RedemptionBatch)
            .order_by(RedemptionBatch.created_at.desc(), RedemptionBatch.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ):
            redeemed = (
                session.scalar(
                    select(func.count())
                    .select_from(RedemptionCode)
                    .where(RedemptionCode.batch_id == b.id, RedemptionCode.status == "REDEEMED")
                )
                or 0
            )
            items.append(
                {
                    "public_batch_id": b.public_batch_id,
                    "name": b.name,
                    "active": b.active,
                    "quantity": b.quantity,
                    "credits_per_code": b.credits_per_code,
                    "redeemed": redeemed,
                    "expires_at": b.expires_at.isoformat() if b.expires_at else None,
                }
            )
        return AdminPage(items=items, total=total, page=page, page_size=page_size)


@router.post("/batches", response_model=AdminResult, dependencies=[Depends(csrf)])
def create_batch(body: BatchCreateCommand, request: Request, user: Owner) -> AdminResult:
    admin = service(request)
    return AdminResult(
        data=admin.mutate(
            user.id,
            request.cookies[COOKIE],
            "batch.create",
            "batch",
            body,
            lambda s: admin.batch(s, pepper(config(request)), body),
            secrets_once=True,
        )
    )


@router.post(
    "/batches/{public_id}/disable", response_model=AdminResult, dependencies=[Depends(csrf)]
)
def disable_batch(public_id: str, body: AdminCommand, request: Request, user: Owner) -> AdminResult:
    admin = service(request)
    return AdminResult(
        data=admin.mutate(
            user.id,
            request.cookies[COOKIE],
            "batch.disable",
            public_id,
            body,
            lambda s: admin.disable_batch(s, public_id),
        )
    )


@router.get("/jobs", response_model=AdminPage)
def jobs(
    request: Request,
    user: Owner,
    page: Page = 1,
    page_size: Size = 25,
    status: Annotated[str, Query(pattern="^(all|QUEUED|RUNNING|COMPLETED|FAILED)$")] = "all",
) -> AdminPage:
    with sessions(request)() as session:
        query = select(ResearchJob)
        if status != "all":
            query = query.where(ResearchJob.status == status)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        items: list[dict[str, JsonValue]] = [
            {
                "id": str(j.id),
                "kind": j.kind,
                "provider": j.provider,
                "status": j.status,
                "progress": j.progress,
                "attempts": j.attempts,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in session.scalars(
                query.order_by(ResearchJob.created_at.desc(), ResearchJob.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ]
        return AdminPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/audit", response_model=AdminPage)
def audit_log(request: Request, user: Owner, page: Page = 1, page_size: Size = 25) -> AdminPage:
    with sessions(request)() as session:
        total = session.scalar(select(func.count()).select_from(AdminAudit)) or 0
        items: list[dict[str, JsonValue]] = [
            {
                "id": str(a.id),
                "actor_id": str(a.actor_id) if a.actor_id else None,
                "action": a.action,
                "target": a.target,
                "outcome": a.outcome,
                "details": a.details,
                "created_at": a.created_at.isoformat(),
            }
            for a in session.scalars(
                select(AdminAudit)
                .order_by(AdminAudit.created_at.desc(), AdminAudit.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ]
        return AdminPage(items=items, total=total, page=page, page_size=page_size)
