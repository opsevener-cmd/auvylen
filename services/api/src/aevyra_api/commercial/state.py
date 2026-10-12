from aevyra_contracts.commercial import OrderStatus

from aevyra_api.commercial.models import Order, now


class DomainError(Exception):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset({OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED}),
    OrderStatus.PENDING_PAYMENT: frozenset({OrderStatus.PAID, OrderStatus.CANCELLED}),
    OrderStatus.PAID: frozenset({OrderStatus.FULFILLING}),
    OrderStatus.FULFILLING: frozenset({OrderStatus.COMPLETED, OrderStatus.FAILED}),
    OrderStatus.FAILED: frozenset({OrderStatus.FULFILLING}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REFUNDED: frozenset(),
}


def transition(order: Order, target: OrderStatus) -> None:
    current = OrderStatus(order.status)
    if target not in TRANSITIONS[current]:
        raise DomainError(f"Invalid order transition: {current} to {target}")
    order.status = target
    if target == OrderStatus.PAID:
        order.paid_at = now()
    if target == OrderStatus.COMPLETED:
        order.completed_at = now()
