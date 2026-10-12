from dataclasses import asdict
from uuid import UUID

from aevyra_contracts.commercial import EmptyRequest
from aevyra_contracts.research import ProviderView, ResearchJobView, ResearchRequest, ResearchStatus
from aevyra_inference.providers import ProviderCatalog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from aevyra_api.commercial.state import DomainError
from aevyra_api.research.jobs import ResearchQueue, authorized
from aevyra_api.research.models import ResearchJob
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions

router = APIRouter(prefix="/api/v1/research", tags=["authorized research"])


@router.get("/status", response_model=ResearchStatus)
def status(request: Request, user: CurrentUser) -> ResearchStatus:
    settings = config(request)
    catalog = ProviderCatalog(settings.enabled_model_providers, settings.private_model_root)
    with sessions(request)() as session:
        allowed = settings.research_mode and authorized(session, user.id)
    return ResearchStatus(
        enabled=settings.research_mode,
        authorized=allowed,
        synthetic_available=allowed and settings.api_environment != "production",
        providers=[ProviderView(**asdict(item)) for item in catalog.statuses()],
    )


@router.post("/jobs", response_model=ResearchJobView, status_code=202, dependencies=[Depends(csrf)])
def submit(body: ResearchRequest, request: Request, user: CurrentUser) -> ResearchJobView:
    rate(request, "analysis", 30, user.public_user_id)
    job = ResearchQueue(sessions(request), config(request)).enqueue(
        user.id, body.provider, str(body.idempotency_key)
    )
    return ResearchJobView.model_validate(job)


@router.get("/jobs", response_model=list[ResearchJobView])
def history(request: Request, user: CurrentUser) -> list[ResearchJobView]:
    with sessions(request)() as session:
        return [
            ResearchJobView.model_validate(job)
            for job in session.scalars(
                select(ResearchJob)
                .where(ResearchJob.user_id == user.id)
                .order_by(ResearchJob.created_at.desc())
                .limit(50)
            )
        ]


@router.get("/jobs/{job_id}", response_model=ResearchJobView)
def result(job_id: UUID, request: Request, user: CurrentUser) -> ResearchJobView:
    with sessions(request)() as session:
        job = session.scalar(
            select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user.id)
        )
        if job is None:
            raise DomainError("Research job not found", 404)
        return ResearchJobView.model_validate(job)


@router.post("/jobs/{job_id}/cancel", response_model=ResearchJobView, dependencies=[Depends(csrf)])
def cancel(
    job_id: UUID, body: EmptyRequest, request: Request, user: CurrentUser
) -> ResearchJobView:
    job = ResearchQueue(sessions(request), config(request)).cancel(user.id, job_id)
    return ResearchJobView.model_validate(job)
