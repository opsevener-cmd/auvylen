import hashlib
import hmac
from collections.abc import Mapping

from aevyra_contracts.commercial import PaymentStatus

from aevyra_api.commercial.state import DomainError
from aevyra_api.payments.provider import (
    PaymentProvider,
    PaymentRequest,
    ProviderPayment,
    ProviderRefund,
    VerifiedPaymentEvent,
)


class MockPaymentProvider(PaymentProvider):
    """The local persisted attempt is the mock ledger. No real funds are moved."""

    slug = "mock"

    def __init__(self, signing_key: bytes) -> None:
        self._signing_key = signing_key

    def create_payment(self, request: PaymentRequest) -> ProviderPayment:
        return ProviderPayment(
            f"mock_{request.attempt_id.hex}",
            request.amount,
            request.currency,
            PaymentStatus.PENDING,
        )

    def query_payment(self, payment: ProviderPayment) -> ProviderPayment:
        return payment

    def refund(self, payment: ProviderPayment, refund_reference: str) -> ProviderRefund:
        if payment.status != PaymentStatus.SUCCEEDED:
            raise DomainError("Only successful mock payments can be refunded")
        return ProviderRefund(f"mock_refund_{refund_reference}", payment.amount, payment.currency)

    def success_event(self, payment: ProviderPayment) -> VerifiedPaymentEvent:
        event = VerifiedPaymentEvent(
            provider=self.slug,
            provider_event_id=f"success_{payment.provider_payment_id}",
            provider_payment_id=payment.provider_payment_id,
            event_type="payment.succeeded",
            amount=payment.amount,
            currency=payment.currency,
        )
        payload = event.model_dump_json().encode()
        signature = hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()
        return self.handle_webhook(payload, {"x-mock-signature": signature})

    def handle_webhook(self, payload: bytes, headers: Mapping[str, str]) -> VerifiedPaymentEvent:
        expected = hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, headers.get("x-mock-signature", "")):
            raise DomainError("Invalid payment notification signature", 400)
        event = VerifiedPaymentEvent.model_validate_json(payload)
        if event.provider != self.slug:
            raise DomainError("Payment provider mismatch", 400)
        return event
