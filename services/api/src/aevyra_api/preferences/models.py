from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.commercial.models import now
from aevyra_api.database import Base


class PreferenceProject(Base):
    __tablename__ = "preference_projects"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PreferenceDataset(Base):
    __tablename__ = "preference_datasets"
    __table_args__ = (CheckConstraint("rating_min < rating_max", name="ck_dataset_scale"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("preference_projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str] = mapped_column(String(500))
    license: Mapped[str] = mapped_column(String(500))
    rating_min: Mapped[int] = mapped_column(Integer)
    rating_max: Mapped[int] = mapped_column(Integer)
    consent_version: Mapped[str] = mapped_column(String(40))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PreferenceImage(Base):
    __tablename__ = "preference_images"
    __table_args__ = (
        UniqueConstraint("dataset_id", "content_hash", name="uq_dataset_image_content"),
        CheckConstraint("byte_size > 0", name="ck_image_bytes"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("preference_datasets.id"), index=True)
    artifact_id: Mapped[UUID] = mapped_column(Uuid)
    thumbnail_id: Mapped[UUID] = mapped_column(Uuid)
    original_hash: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    subject_group: Mapped[str | None] = mapped_column(String(120))
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_version: Mapped[str] = mapped_column(String(40))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PreferenceRating(Base):
    __tablename__ = "preference_ratings"
    image_id: Mapped[UUID] = mapped_column(ForeignKey("preference_images.id"), primary_key=True)
    score: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class PreferencePair(Base):
    __tablename__ = "preference_pairs"
    __table_args__ = (
        UniqueConstraint("left_id", "right_id", name="uq_preference_pair"),
        CheckConstraint("left_id < right_id", name="ck_pair_canonical_order"),
        CheckConstraint("choice IN ('left','right','equal','skip')", name="ck_pair_choice"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    dataset_id: Mapped[UUID] = mapped_column(ForeignKey("preference_datasets.id"), index=True)
    left_id: Mapped[UUID] = mapped_column(ForeignKey("preference_images.id"))
    right_id: Mapped[UUID] = mapped_column(ForeignKey("preference_images.id"))
    choice: Mapped[str] = mapped_column(String(10))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
