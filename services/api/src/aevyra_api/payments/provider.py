from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from aevyra_contracts.commercial import PaymentStatus
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class PaymentRequest:
    attempt_id: UUID
    order_reference: str
    amount: int
    currency: str


@dataclass(frozen=True)
class ProviderPayment:
    provider_payment_id: str
    amount: int
    currency: str
    status: PaymentStatus


@dataclass(frozen=True)
class ProviderRefund:
    provider_refund_id: str
    amount: int
    currency: str


class VerifiedPaymentEvent(BaseModel):
    """Only adapters create this after verification; never bind it to a public route."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str
    provider_event_id: str = Field(min_length=1, max_length=100)
    provider_payment_id: str
    event_type: str
    amount: int = Field(strict=True, gt=0)
    currency: str


class PaymentProvider(ABC):
    slug: str

    @abstractmethod
    def create_payment(self, request: PaymentRequest) -> ProviderPayment: ...

    @abstractmethod
    def query_payment(self, payment: ProviderPayment) -> ProviderPayment: ...

    @abstractmethod
    def handle_webhook(
        self, payload: bytes, headers: Mapping[str, str]
    ) -> VerifiedPaymentEvent: ...

    @abstractmethod
    def refund(self, payment: ProviderPayment, refund_reference: str) -> ProviderRefund: ...
