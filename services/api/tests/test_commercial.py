from uuid import UUID, uuid4

import pytest
from aevyra_api.commercial.events import PaymentEventProcessor
from aevyra_api.commercial.models import (
    Analysis,
    AnalysisResult,
    Order,
    PaymentAttempt,
    PaymentEvent,
    Product,
)
from aevyra_api.commercial.state import TRANSITIONS, DomainError, transition
from aevyra_api.config import Settings
from aevyra_api.main import create_app
from aevyra_api.payments.future import AlipayProvider, WeChatPayProvider
from aevyra_api.payments.provider import PaymentRequest
from aevyra_contracts.commercial import OrderStatus, PaymentStatus
from fastapi.testclient import TestClient
from sqlalchemy import func, select

PRODUCT = "aevyra-test-analysis"


def start(commerce):
    order = commerce.orders.create(PRODUCT)
    payment = commerce.orders.create_payment(order.public_order_id)
    return order, payment


def test_backend_price_and_reject_overrides(commerce) -> None:
    products = commerce.client.get("/api/v1/products").json()
    assert products[0]["price_amount"] == 100
    order = commerce.client.post("/api/v1/orders", json={"product_slug": PRODUCT})
    assert order.status_code == 201
    assert order.json()["amount"] == 100
    assert order.json()["currency"] == "CNY"
    assert order.json()["status"] == "PENDING_PAYMENT"
    for extra in (
        {"amount": 1},
        {"price_amount": 1},
        {"provider": "alipay"},
        {"status": "PAID"},
        {"engine_version": "forged"},
    ):
        forged = commerce.client.post("/api/v1/orders", json={"product_slug": PRODUCT, **extra})
        assert forged.status_code == 422
    with commerce.sessions.begin() as session:
        product = session.scalar(select(Product).where(Product.slug == PRODUCT))
        product.price_amount = 690
    assert commerce.orders.get(order.json()["public_order_id"]).amount == 100
    assert commerce.orders.create(PRODUCT).amount == 690


def test_inactive_product_and_not_found(commerce) -> None:
    assert (
        commerce.client.post("/api/v1/orders", json={"product_slug": "missing"}).status_code == 404
    )
    with commerce.sessions.begin() as session:
        session.scalar(select(Product).where(Product.slug == PRODUCT)).active = False
    assert commerce.client.post("/api/v1/orders", json={"product_slug": PRODUCT}).status_code == 404
    assert commerce.client.get("/api/v1/orders/missing").status_code == 404
    assert commerce.client.get(f"/api/v1/analyses/{uuid4()}").status_code == 404


@pytest.mark.parametrize(
    "source,target",
    [(source, target) for source, targets in TRANSITIONS.items() for target in targets],
)
def test_valid_transitions(source, target) -> None:
    order = Order(status=source)
    transition(order, target)
    assert order.status == target


@pytest.mark.parametrize(
    "source,target",
    [
        (OrderStatus.CREATED, OrderStatus.PAID),
        (OrderStatus.PENDING_PAYMENT, OrderStatus.COMPLETED),
        (OrderStatus.COMPLETED, OrderStatus.PAID),
        (OrderStatus.CANCELLED, OrderStatus.PENDING_PAYMENT),
    ],
)
def test_invalid_transitions(source, target) -> None:
    order = Order(status=source)
    with pytest.raises(DomainError):
        transition(order, target)
    assert order.status == source


def test_payment_creation_reuses_pending_attempt(commerce) -> None:
    order, payment = start(commerce)
    repeated = commerce.client.post(f"/api/v1/orders/{order.public_order_id}/payments", json={})
    assert repeated.status_code == 200
    assert repeated.json()["payment_id"] == str(payment.payment_id)
    assert payment.amount == 100
    assert payment.status == PaymentStatus.PENDING
    assert (
        commerce.provider.query_payment(commerce.orders.payment_details(payment.payment_id)).status
        == PaymentStatus.PENDING
    )


def test_success_duplicate_and_persisted_result(commerce) -> None:
    order, payment = start(commerce)
    endpoint = f"/api/v1/dev/payments/{payment.payment_id}/simulate-success"
    first = commerce.client.post(endpoint, json={})
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "COMPLETED"
    assert body["paid_at"] and body["completed_at"]
    repeated = commerce.client.post(endpoint, json={})
    assert repeated.status_code == 200
    assert repeated.json()["analysis_id"] == body["analysis_id"]
    assert repeated.json()["paid_at"] == body["paid_at"]
    assert commerce.engine.calls == 1
    result = commerce.client.get(f"/api/v1/analyses/{body['analysis_id']}/result")
    assert result.status_code == 200
    assert result.json()["metadata"]["synthetic"] is True
    assert result.json()["engine_version"] == "0.1.0"
    assert result.json()["metadata"]["scored_at"]
    assert (
        commerce.client.get(f"/api/v1/analyses/{body['analysis_id']}").json()["status"]
        == "COMPLETED"
    )
    with commerce.sessions() as session:
        for model in (Analysis, AnalysisResult, PaymentEvent):
            assert session.scalar(select(func.count()).select_from(model)) == 1
        assert session.scalar(select(PaymentAttempt)).status == "SUCCEEDED"
        assert session.scalar(select(PaymentEvent)).processing_status == "PROCESSED"
    assert (
        commerce.client.post(
            f"/api/v1/orders/{order.public_order_id}/payments", json={}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "changes", [{"amount": 99}, {"currency": "USD"}, {"event_type": "unknown"}]
)
def test_mismatches_record_rejected_event(commerce, changes) -> None:
    order, payment = start(commerce)
    notification = commerce.provider.success_event(
        commerce.orders.payment_details(payment.payment_id)
    )
    notification = notification.model_copy(update=changes)
    with pytest.raises(DomainError, match="rejected"):
        commerce.events.process(notification)
    assert commerce.orders.get(order.public_order_id).status == OrderStatus.PENDING_PAYMENT
    assert commerce.engine.calls == 0
    with commerce.sessions() as session:
        assert session.scalar(select(PaymentEvent)).processing_status == "REJECTED"
        assert session.scalar(select(PaymentAttempt)).status == "PENDING"
    with pytest.raises(DomainError):
        commerce.events.process(notification)


def test_forged_frontend_success_rejected(commerce) -> None:
    order, payment = start(commerce)
    endpoint = f"/api/v1/dev/payments/{payment.payment_id}/simulate-success"
    assert (
        commerce.client.post(endpoint, json={"amount": 1, "status": "SUCCEEDED"}).status_code == 422
    )
    assert (
        commerce.client.post(
            f"/api/v1/orders/{order.public_order_id}", json={"status": "PAID"}
        ).status_code
        == 405
    )
    assert commerce.client.post("/api/v1/analyses", json={"display_score": 10}).status_code == 404
    assert (
        commerce.client.post(
            "/api/v1/payments/webhooks/mock", json={"status": "SUCCEEDED"}
        ).status_code
        == 404
    )
    with pytest.raises(DomainError, match="signature"):
        commerce.provider.handle_webhook(b'{"status":"SUCCEEDED"}', {})
    assert commerce.orders.get(order.public_order_id).status == OrderStatus.PENDING_PAYMENT


def test_distinct_event_for_same_success_does_not_rescore(commerce) -> None:
    order, payment = start(commerce)
    notification = commerce.provider.success_event(
        commerce.orders.payment_details(payment.payment_id)
    )
    commerce.events.process(notification)
    commerce.events.process(
        notification.model_copy(update={"provider_event_id": "different-event"})
    )
    assert commerce.engine.calls == 1
    assert commerce.orders.get(order.public_order_id).status == OrderStatus.COMPLETED


def test_event_id_collision_is_rejected(commerce) -> None:
    _, payment = start(commerce)
    notification = commerce.provider.success_event(
        commerce.orders.payment_details(payment.payment_id)
    )
    commerce.events.process(notification)
    with pytest.raises(DomainError, match="collision"):
        commerce.events.process(notification.model_copy(update={"amount": 2}))
    assert commerce.engine.calls == 1


def test_scoring_failure_keeps_payment_and_allows_explicit_retry(commerce) -> None:
    order, payment = start(commerce)
    commerce.engine.fail = True
    endpoint = f"/api/v1/dev/payments/{payment.payment_id}/simulate-success"
    response = commerce.client.post(endpoint, json={})
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    analysis_id = response.json()["analysis_id"]
    assert response.json()["paid_at"]
    assert response.json()["completed_at"] is None
    assert commerce.client.get(f"/api/v1/analyses/{analysis_id}/result").status_code == 404
    analysis = commerce.client.get(f"/api/v1/analyses/{analysis_id}").json()
    assert analysis["status"] == "FAILED"
    assert "sensitive" not in analysis["failure_reason"]
    commerce.client.post(endpoint, json={})
    assert commerce.engine.calls == 1
    with commerce.sessions() as session:
        assert session.scalar(select(PaymentAttempt)).status == "SUCCEEDED"
        assert session.scalar(select(PaymentEvent)).processing_status == "PROCESSED"
        order_id = session.scalar(select(Order)).id
    commerce.engine.fail = False
    commerce.fulfillment.fulfill(order_id, retry_failed=True)
    assert commerce.orders.get(order.public_order_id).status == OrderStatus.COMPLETED
    assert commerce.orders.get(order.public_order_id).analysis_id == UUID(analysis_id)
    assert commerce.engine.calls == 2


def test_unpaid_order_cannot_be_fulfilled(commerce) -> None:
    order, _ = start(commerce)
    with commerce.sessions() as session:
        order_id = session.scalar(
            select(Order).where(Order.public_order_id == order.public_order_id)
        ).id
    with pytest.raises(DomainError, match="confirmed payment"):
        commerce.fulfillment.fulfill(order_id)
    assert commerce.engine.calls == 0


def test_mock_refund_and_future_adapters(commerce) -> None:
    _, payment = start(commerce)
    pending = commerce.orders.payment_details(payment.payment_id)
    with pytest.raises(DomainError):
        commerce.provider.refund(pending, "test")
    commerce.events.process(commerce.provider.success_event(pending))
    successful = commerce.orders.payment_details(payment.payment_id)
    refund = commerce.provider.refund(successful, "test")
    assert refund.amount == 100
    assert commerce.provider.refund(successful, "test") == refund
    for provider in (WeChatPayProvider(), AlipayProvider()):
        with pytest.raises(NotImplementedError):
            provider.create_payment(PaymentRequest(uuid4(), "test", 100, "CNY"))


def test_production_disables_commercial_routes() -> None:
    app = create_app(
        Settings(
            api_environment="production",
            database_url="postgresql+psycopg://local:testing-only-long-password@127.0.0.1/aevyra",
            redis_url="redis://127.0.0.1:6379/0",
            cors_origins=[],
            _env_file=None,
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/products").status_code == 404
        assert (
            client.post(f"/api/v1/dev/payments/{uuid4()}/simulate-success", json={}).status_code
            == 404
        )
        assert client.get("/health").status_code == 200


def test_payment_commit_survives_fulfillment_crash(commerce) -> None:
    class CrashedFulfillment:
        def fulfill(self, order_id, *, retry_failed=False):
            raise RuntimeError("process unavailable")

    order, payment = start(commerce)
    notification = commerce.provider.success_event(
        commerce.orders.payment_details(payment.payment_id)
    )
    processor = PaymentEventProcessor(commerce.sessions, CrashedFulfillment())
    with pytest.raises(RuntimeError):
        processor.process(notification)
    assert commerce.orders.get(order.public_order_id).status == OrderStatus.PAID
    with commerce.sessions() as session:
        assert session.scalar(select(PaymentEvent)).processing_status == "PROCESSED"
        assert session.scalar(select(PaymentAttempt)).status == "SUCCEEDED"
        assert session.scalar(select(func.count()).select_from(Analysis)) == 0
    commerce.events.process(notification)
    assert commerce.engine.calls == 1
    assert commerce.orders.get(order.public_order_id).status == OrderStatus.COMPLETED
