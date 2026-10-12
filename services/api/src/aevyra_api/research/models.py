from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.commercial.models import now
from aevyra_api.database import Base


class ResearchAccess(Base):
    __tablename__ = "research_access"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_research_request"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETED','FAILED')", name="ck_job_status"
        ),
        CheckConstraint("kind IN ('SCORE','TRAIN')", name="ck_job_kind"),
        CheckConstraint("queue IN ('cpu','gpu')", name="ck_job_queue"),
        CheckConstraint("attempts >= 0", name="ck_job_attempts"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="SCORE")
    provider: Mapped[str] = mapped_column(String(100))
    queue: Mapped[str] = mapped_column(String(20), default="cpu")
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON)
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    phase: Mapped[str] = mapped_column(String(100), default="Queued", server_default="Queued")
    result: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
