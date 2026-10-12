"""PostgreSQL durable queue. Execution is at-least-once; completion is fenced."""

from dataclasses import dataclass
from datetime import UTC, timedelta
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.research.models import ResearchAccess, ResearchJob


def authorized(session: Session, user_id: UUID) -> bool:
    user = session.get(User, user_id)
    access = session.get(ResearchAccess, user_id)
    return bool(user and user.disabled_at is None and access and access.enabled)


@dataclass(frozen=True)
class JobLease:
    id: UUID
    user_id: UUID
    provider: str
    kind: str
    token: UUID


class ResearchQueue:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings) -> None:
        self.sessions = sessions
        self.settings = settings

    def enqueue(self, user_id: UUID, provider: str, request_key: str) -> ResearchJob:
        if not self.settings.research_mode:
            raise DomainError("Research mode unavailable", 404)
        # Real providers need reviewed adapters AND an authorized image-import path.
        # Neither exists yet; no fallback to the synthetic engine is permitted.
        if provider != "mock":
            raise DomainError("Model provider unavailable; real inference not installed", 503)
        if self.settings.api_environment == "production":
            raise DomainError("Synthetic research unavailable in production", 404)
        with self.sessions.begin() as session:
            user = session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or not authorized(session, user_id):
                raise DomainError("Research access required", 403)
            existing = session.scalar(
                select(ResearchJob).where(
                    ResearchJob.user_id == user_id, ResearchJob.request_key == request_key
                )
            )
            if existing:
                if existing.provider != provider:
                    raise DomainError("Research request key conflict", 409)
                return existing
            pending = (
                session.scalar(
                    select(func.count())
                    .select_from(ResearchJob)
                    .where(
                        ResearchJob.user_id == user_id,
                        ResearchJob.status.in_(["QUEUED", "RUNNING"]),
                    )
                )
                or 0
            )
            daily = (
                session.scalar(
                    select(func.count())
                    .select_from(ResearchJob)
                    .where(
                        ResearchJob.user_id == user_id,
                        ResearchJob.created_at >= now() - timedelta(days=1),
                    )
                )
                or 0
            )
            if (
                pending >= self.settings.research_max_pending
                or daily >= self.settings.research_daily_limit
            ):
                raise DomainError("Research resource limit reached", 429)
            job = ResearchJob(
                user_id=user_id, request_key=request_key, provider=provider, queue="cpu"
            )
            session.add(job)
            session.flush()
            return job

    def claim(self) -> JobLease | None:
        if not self.settings.research_mode:
            return None
        with self.sessions.begin() as session:
            while True:
                job = session.scalar(
                    select(ResearchJob)
                    .where(
                        ResearchJob.queue == self.settings.worker_queue,
                        or_(
                            ResearchJob.status == "QUEUED",
                            (ResearchJob.status == "RUNNING") & (ResearchJob.lease_until < now()),
                        ),
                    )
                    .order_by(ResearchJob.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if job is None:
                    return None
                if job.attempts >= 3 or not authorized(session, job.user_id):
                    job.status = "FAILED"
                    job.failure_reason = "Retry limit or research authorization unavailable"
                    job.completed_at = now()
                    session.flush()
                    continue
                job.status = "RUNNING"
                job.attempts += 1
                job.lease_token = uuid4()
                job.lease_until = now() + timedelta(seconds=self.settings.job_lease_seconds)
                return JobLease(job.id, job.user_id, job.provider, job.kind, job.lease_token)

    def finish(self, lease: JobLease, result: dict[str, JsonValue] | None) -> bool:
        with self.sessions.begin() as session:
            job = session.scalar(
                select(ResearchJob).where(ResearchJob.id == lease.id).with_for_update()
            )
            if job is None or job.status != "RUNNING" or job.lease_token != lease.token:
                return False  # A stale worker can never overwrite the newer lease's result.
            deadline = job.lease_until
            if deadline is not None and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)  # SQLite test-fixture normalization.
            if deadline is None or deadline < now():
                return False
            allowed = authorized(session, job.user_id)
            job.result = result if allowed else None
            job.status = "COMPLETED" if result is not None and allowed else "FAILED"
            job.failure_reason = (
                None if job.status == "COMPLETED" else "Research execution unavailable or failed"
            )
            job.completed_at = now()
            job.lease_until = None
            job.lease_token = None
            return True
