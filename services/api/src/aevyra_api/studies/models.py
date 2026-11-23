"""New collection tables only; no changes to accounts, Credits or personal models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.commercial.models import now
from aevyra_api.database import Base


class Study(Base):
    __tablename__ = "collection_studies"
    __table_args__ = (
        CheckConstraint("partition IN ('development','holdout')", name="ck_study_partition"),
        CheckConstraint(
            "status IN ('DRAFT','OPEN','PAUSED','CLOSED','SEALED')", name="ck_study_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    custodian_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120))
    partition: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    fixture_only: Mapped[bool] = mapped_column(Boolean, default=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    invite_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    seal_sha256: Mapped[str | None] = mapped_column(String(64))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConsentVersion(Base):
    __tablename__ = "collection_consent_versions"
    __table_args__ = (UniqueConstraint("study_id", "version", name="uq_study_consent_version"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    text_en: Mapped[str] = mapped_column(Text)
    text_zh: Mapped[str] = mapped_column(Text)
    contact_en: Mapped[str] = mapped_column(String(300))
    contact_zh: Mapped[str] = mapped_column(String(300))
    rights_reference: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Person(Base):
    __tablename__ = "collection_people"
    __table_args__ = (
        CheckConstraint(
            "partition IN ('development','holdout')", name="ck_collection_person_partition"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    partition: Mapped[str] = mapped_column(String(16))
    identity_digest: Mapped[str | None] = mapped_column(String(64), unique=True)


class Member(Base):
    __tablename__ = "collection_members"
    __table_args__ = (
        UniqueConstraint("study_id", "person_id", "role", name="uq_collection_member"),
        CheckConstraint(
            "role IN ('contributor','rater','custodian')", name="ck_collection_member_role"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("collection_people.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    consent_id: Mapped[UUID] = mapped_column(ForeignKey("collection_consent_versions.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_reference: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Receipt(Base):
    __tablename__ = "collection_receipts"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("collection_members.id"), index=True)
    consent_id: Mapped[UUID] = mapped_column(ForeignKey("collection_consent_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Photo(Base):
    __tablename__ = "collection_photos"
    __table_args__ = (UniqueConstraint("member_id", "request_key", name="uq_collection_upload"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("collection_members.id"), index=True)
    consent_id: Mapped[UUID] = mapped_column(ForeignKey("collection_consent_versions.id"))
    request_key: Mapped[str] = mapped_column(String(40))
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid)
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    review: Mapped[str] = mapped_column(String(16), default="PENDING")
    pose: Mapped[str] = mapped_column(String(16))
    lighting: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Assignment(Base):
    __tablename__ = "collection_assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ASSIGNED','SAVED','SKIPPED','CANCELLED')",
            name="ck_collection_assignment_status",
        ),
        CheckConstraint("score IS NULL OR (score >= 1 AND score <= 7)", name="ck_collection_score"),
        Index(
            "uq_collection_active_assignment",
            "member_id",
            unique=True,
            postgresql_where=text("status='ASSIGNED'"),
            sqlite_where=text("status='ASSIGNED'"),
        ),
        Index(
            "uq_collection_primary_rating",
            "member_id",
            "photo_id",
            unique=True,
            postgresql_where=text("repeat = false AND status IN ('SAVED','SKIPPED')"),
            sqlite_where=text("repeat = 0 AND status IN ('SAVED','SKIPPED')"),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("collection_members.id"), index=True)
    photo_id: Mapped[UUID] = mapped_column(ForeignKey("collection_photos.id"), index=True)
    consent_id: Mapped[UUID] = mapped_column(ForeignKey("collection_consent_versions.id"))
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repeat: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="ASSIGNED")
    score: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StudyExport(Base):
    __tablename__ = "collection_exports"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    request_key: Mapped[str] = mapped_column(String(40), unique=True)
    artifact_id: Mapped[UUID | None] = mapped_column(Uuid)
    sha256: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    images: Mapped[int] = mapped_column(Integer)
    subjects: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StudyAudit(Base):
    __tablename__ = "collection_audit"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    actor_ref: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(60))
    request_key: Mapped[str | None] = mapped_column(String(40), unique=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StudyGarbage(Base):
    """Durable erasure outbox: database access is revoked before physical cleanup."""

    __tablename__ = "collection_garbage"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    study_id: Mapped[UUID] = mapped_column(ForeignKey("collection_studies.id"), index=True)
    namespace: Mapped[str] = mapped_column(String(32))
    artifact_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
