from uuid import UUID, uuid4

from aevyra_contracts.commercial import (
    OrderStatus,
    OrderView,
    PaymentStatus,
    PaymentView,
    ProductView,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import Analysis, Order, PaymentAttempt, Product
from aevyra_api.commercial.state import DomainError, transition
from aevyra_api.payments.provider import PaymentProvider, PaymentRequest, ProviderPayment


class OrderService:
    def __init__(self, sessions: sessionmaker[Session], provider: PaymentProvider) -> None:
        self.sessions = sessions
        self.provider = provider

    def products(self) -> list[ProductView]:
        with self.sessions() as session:
            return [
                ProductView.model_validate(p)
                for p in session.scalars(
                    select(Product).where(Product.active.is_(True)).order_by(Product.slug)
                )
            ]

    def create(self, product_slug: str) -> OrderView:
        with self.sessions.begin() as session:
            product = session.scalar(
                select(Product)
                .where(Product.slug == product_slug, Product.active.is_(True))
                .with_for_update()
            )
            if product is None:
                raise DomainError("Active product not found", 404)
            order = Order(
                public_order_id=f"av_{uuid4().hex}",
                product_id=product.id,
                provider=self.provider.slug,
                amount=product.price_amount,
                currency=product.currency,
                status=OrderStatus.CREATED,
            )
            transition(order, OrderStatus.PENDING_PAYMENT)
            session.add(order)
            session.flush()
            return self.view(session, order)

    def get(self, public_id: str) -> OrderView:
        with self.sessions() as session:
            order = session.scalar(select(Order).where(Order.public_order_id == public_id))
            if order is None:
                raise DomainError("Order not found", 404)
            return self.view(session, order)

    def create_payment(self, public_id: str) -> PaymentView:
        with self.sessions.begin() as session:
            order = session.scalar(
                select(Order).where(Order.public_order_id == public_id).with_for_update()
            )
            if order is None:
                raise DomainError("Order not found", 404)
            if order.status != OrderStatus.PENDING_PAYMENT:
                raise DomainError("Order is not awaiting payment")
            existing = session.scalar(
                select(PaymentAttempt).where(
                    PaymentAttempt.order_id == order.id,
                    PaymentAttempt.status == PaymentStatus.PENDING,
                )
            )
            if existing is not None:
                return self.payment_view(existing)
            attempt_id = uuid4()
            payment = self.provider.create_payment(
                PaymentRequest(attempt_id, order.public_order_id, order.amount, order.currency)
            )
            if payment.status != PaymentStatus.PENDING or (payment.amount, payment.currency) != (
                order.amount,
                order.currency,
            ):
                raise DomainError("Provider payment terms do not match order")
            attempt = PaymentAttempt(
                id=attempt_id,
                order_id=order.id,
                provider=order.provider,
                provider_payment_id=payment.provider_payment_id,
                status=payment.status,
                amount=order.amount,
                currency=order.currency,
            )
            session.add(attempt)
            session.flush()
            return self.payment_view(attempt)

    def payment_details(self, payment_id: UUID) -> ProviderPayment:
        with self.sessions() as session:
            payment = session.get(PaymentAttempt, payment_id)
            if payment is None:
                raise DomainError("Payment attempt not found", 404)
            return ProviderPayment(
                payment.provider_payment_id,
                payment.amount,
                payment.currency,
                PaymentStatus(payment.status),
            )

    @staticmethod
    def payment_view(payment: PaymentAttempt) -> PaymentView:
        return PaymentView(
            payment_id=payment.id,
            provider=payment.provider,
            status=PaymentStatus(payment.status),
            amount=payment.amount,
            currency=payment.currency,
        )

    @staticmethod
    def view(session: Session, order: Order) -> OrderView:
        product = session.get(Product, order.product_id)
        if product is None:
            raise DomainError("Order product not found", 409)
        analysis = session.scalar(select(Analysis).where(Analysis.order_id == order.id))
        return OrderView(
            public_order_id=order.public_order_id,
            product=ProductView.model_validate(product),
            provider=order.provider,
            amount=order.amount,
            currency=order.currency,
            status=OrderStatus(order.status),
            created_at=order.created_at,
            paid_at=order.paid_at,
            completed_at=order.completed_at,
            analysis_id=analysis.id if analysis else None,
        )
