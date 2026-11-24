from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.commercial.models import now
from aevyra_api.database import Base


class PhotoCheckConsent(Base):
    """The user's own 18+ and processing statements, one row per consent version."""

    __tablename__ = "photo_check_consents"
    __table_args__ = (
        UniqueConstraint("user_id", "consent_version", name="uq_photo_check_consent"),
        CheckConstraint(
            "adult_confirmed AND processing_accepted", name="ck_photo_check_consent_given"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    consent_version: Mapped[str] = mapped_column(String(40))
    adult_confirmed: Mapped[bool] = mapped_column(Boolean)
    processing_accepted: Mapped[bool] = mapped_column(Boolean)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PhotoCheckBudgetDay(Base):
    """Global spend per UTC day in integer micro-USD. Locked for every reservation."""

    __tablename__ = "photo_check_budget_days"
    __table_args__ = (
        CheckConstraint(
            "spent_micro_usd >= 0 AND reserved_micro_usd >= 0", name="ck_photo_check_budget"
        ),
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    spent_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_micro_usd: Mapped[int] = mapped_column(BigInteger, default=0)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PhotoCheckAnalysis(Base):
    """One provider call: the spend ledger entry and the per-user daily count.

    Photos are never stored. The result holds scores and tips only and is cleared after
    the retention period; the cost record stays for auditing.
    """

    __tablename__ = "photo_check_analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RESERVED','COMPLETED','FAILED')", name="ck_photo_check_status"
        ),
        CheckConstraint("photo_count BETWEEN 1 AND 5", name="ck_photo_check_count"),
        Index("ix_photo_check_user_day", "user_id", "day"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16))
    photo_count: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8))
    model: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(40))
    consent_version: Mapped[str] = mapped_column(String(40))
    reserved_micro_usd: Mapped[int] = mapped_column(BigInteger)
    cost_micro_usd: Mapped[int | None] = mapped_column(BigInteger)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[dict[str, object] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
