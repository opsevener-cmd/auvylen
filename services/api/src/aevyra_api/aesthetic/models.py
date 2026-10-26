from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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


class AestheticAnalysis(Base):
    """Owner-scoped request. The image is private and deleted once scoring is final."""

    __tablename__ = "aesthetic_analyses"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_aesthetic_request"),
        CheckConstraint("width > 0 AND height > 0", name="ck_aesthetic_dimensions"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("research_jobs.id"), unique=True)
    request_key: Mapped[str] = mapped_column(String(80))
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid)
    image_sha256: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    consent_version: Mapped[str] = mapped_column(String(60))
    model_version: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
