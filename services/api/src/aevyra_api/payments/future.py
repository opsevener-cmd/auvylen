from collections.abc import Mapping

from aevyra_api.payments.provider import (
    PaymentProvider,
    PaymentRequest,
    ProviderPayment,
    ProviderRefund,
    VerifiedPaymentEvent,
)


class FuturePaymentProvider(PaymentProvider):
    """Deliberately inert: credentials, verification and network calls are not implemented."""

    def create_payment(self, request: PaymentRequest) -> ProviderPayment:
        raise NotImplementedError("Real payments are not available in Phase 1")

    def query_payment(self, payment: ProviderPayment) -> ProviderPayment:
        raise NotImplementedError("Real payments are not available in Phase 1")

    def handle_webhook(self, payload: bytes, headers: Mapping[str, str]) -> VerifiedPaymentEvent:
        raise NotImplementedError("Provider signature verification must be implemented first")

    def refund(self, payment: ProviderPayment, refund_reference: str) -> ProviderRefund:
        raise NotImplementedError("Real refunds are not available in Phase 1")


class WeChatPayProvider(FuturePaymentProvider):
    slug = "wechat"


class AlipayProvider(FuturePaymentProvider):
    slug = "alipay"
