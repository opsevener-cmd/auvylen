from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    FULFILLING = "FULFILLING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class AnalysisStatus(StrEnum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_slug: str = Field(min_length=1, max_length=100)


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    description: str
    product_type: str
    price_amount: int
    currency: str
    active: bool

    @field_serializer("name")
    def display_name(self, value: str) -> str:
        # Presentation alias only: keep the seeded product row and slug unchanged.
        if self.slug == "aevyra-test-analysis" and value == "Aevyra Analysis":
            return "Auvylen Analysis"
        return value


class OrderView(BaseModel):
    public_order_id: str
    product: ProductView
    provider: str
    amount: int
    currency: str
    status: OrderStatus
    created_at: datetime
    paid_at: datetime | None
    completed_at: datetime | None
    analysis_id: UUID | None


class PaymentView(BaseModel):
    payment_id: UUID
    provider: str
    status: PaymentStatus
    amount: int
    currency: str


class AnalysisView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    scoring_engine_slug: str
    status: AnalysisStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None


class AnalysisResultView(BaseModel):
    analysis_id: UUID
    raw_score: float
    display_score: float
    engine_slug: str
    engine_version: str
    calibration_version: str | None
    metadata: dict[str, JsonValue]
    created_at: datetime
