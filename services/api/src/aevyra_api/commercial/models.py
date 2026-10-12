from datetime import UTC, datetime
from uuid import UUID, uuid4

from aevyra_contracts.commercial import AnalysisStatus, OrderStatus, PaymentStatus
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.database import Base


def now() -> datetime:
    return datetime.now(UTC)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now, server_default=func.now()
    )


class Product(Timestamped, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_amount > 0", name="ck_product_price"),
        CheckConstraint("credit_cost > 0", name="ck_product_credit_cost"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000))
    product_type: Mapped[str] = mapped_column(String(40))
    price_amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    credit_cost: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Order(Timestamped, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_order_amount"),
        CheckConstraint(
            "status IN ('CREATED','PENDING_PAYMENT','PAID','FULFILLING',"
            "'COMPLETED','FAILED','CANCELLED','REFUNDED')",
            name="ck_order_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    public_order_id: Mapped[str] = mapped_column(String(40), unique=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    provider: Mapped[str] = mapped_column(String(30))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.CREATED)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentAttempt(Timestamped, Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_provider_payment"),
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        CheckConstraint(
            "status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')", name="ck_payment_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    provider_payment_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default=PaymentStatus.PENDING)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
        CheckConstraint(
            "processing_status IN ('RECEIVED','PROCESSED','REJECTED')", name="ck_event_status"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(30))
    provider_event_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_status: Mapped[str] = mapped_column(String(30), default="RECEIVED")


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED','PROCESSING','COMPLETED','FAILED')", name="ck_analysis_status"
        ),
        CheckConstraint(
            "(order_id IS NOT NULL AND user_id IS NULL AND credit_request_key IS NULL) OR "
            "(order_id IS NULL AND user_id IS NOT NULL AND credit_request_key IS NOT NULL)",
            name="ck_analysis_funding",
        ),
        UniqueConstraint("user_id", "credit_request_key", name="uq_analysis_credit_request"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    order_id: Mapped[UUID | None] = mapped_column(ForeignKey("orders.id"), unique=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    credit_request_key: Mapped[str | None] = mapped_column(String(80))
    scoring_engine_slug: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default=AnalysisStatus.CREATED)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(100))


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analyses.id"), unique=True)
    raw_score: Mapped[float] = mapped_column()
    display_score: Mapped[float] = mapped_column()
    engine_slug: Mapped[str] = mapped_column(String(100))
    engine_version: Mapped[str] = mapped_column(String(100))
    calibration_version: Mapped[str | None] = mapped_column(String(100))
    result_metadata: Mapped[dict[str, JsonValue]] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, server_default=func.now()
    )
