from datetime import datetime
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
    BigInteger,
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

from aevyra_api.commercial.models import Timestamped, now
from aevyra_api.database import Base


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    public_user_id: Mapped[str] = mapped_column(String(40), unique=True)
    login_identifier: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountSession(Base):
    __tablename__ = "sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Wallet(Timestamped, Base):
    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("cached_balance >= 0", name="ck_wallet_nonnegative"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    cached_balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        UniqueConstraint("wallet_id", "idempotency_key", name="uq_credit_idempotency"),
        CheckConstraint("amount <> 0 AND balance_after >= 0", name="ck_credit_amount"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    wallet_id: Mapped[UUID] = mapped_column(ForeignKey("wallets.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    transaction_type: Mapped[str] = mapped_column(String(40))
    reference_type: Mapped[str] = mapped_column(String(40))
    reference_id: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(160))
    balance_after: Mapped[int] = mapped_column(BigInteger)
    transaction_metadata: Mapped[dict[str, JsonValue]] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RedemptionBatch(Base):
    __tablename__ = "redemption_batches"
    __table_args__ = (
        CheckConstraint("credits_per_code > 0 AND quantity > 0", name="ck_batch_quantity"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    public_batch_id: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(64))
    sku: Mapped[str] = mapped_column(String(100))
    credits_per_code: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    batch_metadata: Mapped[dict[str, JsonValue]] = mapped_column("metadata", JSON, default=dict)


class RedemptionCode(Base):
    __tablename__ = "redemption_codes"
    __table_args__ = (
        CheckConstraint("status IN ('AVAILABLE','REDEEMED')", name="ck_redemption_code_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("redemption_batches.id"), index=True)
    lookup_digest: Mapped[str] = mapped_column(String(64), unique=True)
    masked_suffix: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    code_metadata: Mapped[dict[str, JsonValue]] = mapped_column("metadata", JSON, default=dict)


class Redemption(Base):
    __tablename__ = "redemptions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    redemption_code_id: Mapped[UUID] = mapped_column(ForeignKey("redemption_codes.id"), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[UUID] = mapped_column(ForeignKey("wallets.id"))
    credit_transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("credit_transactions.id"), unique=True
    )
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    source_metadata: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
