"""Non-sensitive administrative history and durable free-analysis funding decisions."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.commercial.models import now
from aevyra_api.database import Base


class AdminAudit(Base):
    __tablename__ = "admin_audit"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20))
    request_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, JsonValue]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class FreeAnalysisGrant(Base):
    __tablename__ = "free_analysis_grants"
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analyses.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    product_slug: Mapped[str] = mapped_column(String(100))
    policy: Mapped[str] = mapped_column(String(40), default="owner-product-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
