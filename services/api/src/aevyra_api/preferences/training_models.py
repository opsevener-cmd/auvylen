from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
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


class CustomModel(Base):
    __tablename__ = "custom_preference_models"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_custom_dataset_version"),
        CheckConstraint(
            "state IN ('TRAINING','READY','FAILED','ARCHIVED','DELETED')", name="ck_custom_state"
        ),
        CheckConstraint("version >= 1", name="ck_custom_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("preference_projects.id"))
    dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("preference_datasets.id", ondelete="SET NULL"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default="TRAINING")
    training_job_id: Mapped[UUID] = mapped_column(ForeignKey("research_jobs.id"), unique=True)
    extractor: Mapped[str] = mapped_column(String(100))
    implementation: Mapped[str] = mapped_column(String(100))
    configuration: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    snapshot: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    metrics: Mapped[dict[str, JsonValue] | None] = mapped_column(JSON)
    limitations: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ImageEmbedding(Base):
    __tablename__ = "preference_embeddings"
    __table_args__ = (UniqueConstraint("image_id", "extractor", name="uq_image_extractor"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    image_id: Mapped[UUID] = mapped_column(
        ForeignKey("preference_images.id", ondelete="CASCADE"), index=True
    )
    extractor: Mapped[str] = mapped_column(String(100))
    source_sha256: Mapped[str] = mapped_column(String(64))
    features: Mapped[list[float]] = mapped_column(JSON)
