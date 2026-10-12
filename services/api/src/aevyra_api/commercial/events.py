import logging
from uuid import UUID

from aevyra_contracts.commercial import OrderStatus, PaymentStatus
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.fulfillment import Fulfillment
from aevyra_api.commercial.models import Order, PaymentAttempt, PaymentEvent, now
from aevyra_api.commercial.state import DomainError, transition
from aevyra_api.payments.provider import VerifiedPaymentEvent

logger = logging.getLogger("aevyra.payments")


class PaymentEventProcessor:
    def __init__(self, sessions: sessionmaker[Session], fulfillment: Fulfillment) -> None:
        self.sessions = sessions
        self.fulfillment = fulfillment

    def process(self, notification: VerifiedPaymentEvent) -> str:
        order_id, public_id, rejected = self._record(notification)
        if rejected:
            raise DomainError("Payment event rejected: inconsistent payment terms or state")
        # The payment transaction is committed before inference. Repeated delivery may
        # resume a PAID order after a crash; the fulfillment lock/unique keys make it safe.
        self.fulfillment.fulfill(order_id)
        return public_id

    def _record(self, notification: VerifiedPaymentEvent) -> tuple[UUID, str, bool]:
        with self.sessions.begin() as session:
            attempt = session.scalar(
                select(PaymentAttempt).where(
                    PaymentAttempt.provider == notification.provider,
                    PaymentAttempt.provider_payment_id == notification.provider_payment_id,
                )
            )
            if attempt is None:
                raise DomainError("Payment attempt not found", 404)
            # All modifications for this order acquire the same lock first.
            order = session.scalar(
                select(Order).where(Order.id == attempt.order_id).with_for_update()
            )
            if order is None:
                raise DomainError("Order not found", 404)
            session.refresh(attempt)
            payload = notification.model_dump(mode="json")
            event = session.scalar(
                select(PaymentEvent).where(
                    PaymentEvent.provider == notification.provider,
                    PaymentEvent.provider_event_id == notification.provider_event_id,
                )
            )
            if event is not None:
                if event.payload != payload:
                    raise DomainError("Payment event identifier collision")
                return order.id, order.public_order_id, event.processing_status == "REJECTED"
            event = PaymentEvent(
                provider=notification.provider,
                provider_event_id=notification.provider_event_id,
                event_type=notification.event_type,
                payload=payload,
                processing_status="RECEIVED",
            )
            try:
                with session.begin_nested():
                    session.add(event)
                    session.flush()
            except IntegrityError:
                # Same event ID could arrive for different orders concurrently. The
                # database unique key, not an in-memory cache, arbitrates this race.
                prior = session.scalar(
                    select(PaymentEvent).where(
                        PaymentEvent.provider == notification.provider,
                        PaymentEvent.provider_event_id == notification.provider_event_id,
                    )
                )
                if prior is None or prior.payload != payload:
                    raise DomainError("Payment event identifier collision") from None
                return order.id, order.public_order_id, prior.processing_status == "REJECTED"
            terms_match = (
                notification.event_type == "payment.succeeded"
                and notification.provider == order.provider
                and (notification.amount, notification.currency) == (order.amount, order.currency)
                and (attempt.amount, attempt.currency) == (order.amount, order.currency)
            )
            already_paid = order.paid_at is not None
            valid_state = (
                attempt.status == PaymentStatus.PENDING
                and order.status == OrderStatus.PENDING_PAYMENT
            )
            duplicate_success = attempt.status == PaymentStatus.SUCCEEDED and already_paid
            if not terms_match or not (valid_state or duplicate_success):
                event.processing_status = "REJECTED"
                event.processed_at = now()
                logger.warning("payment_event_rejected", extra={"order_id": str(order.id)})
                return order.id, order.public_order_id, True
            if not duplicate_success:
                attempt.status = PaymentStatus.SUCCEEDED
                transition(order, OrderStatus.PAID)
            event.processing_status = "PROCESSED"
            event.processed_at = now()
            logger.info("payment_event_processed", extra={"order_id": str(order.id)})
            return order.id, order.public_order_id, False
