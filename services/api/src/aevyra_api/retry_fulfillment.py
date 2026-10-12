"""Explicit local operator retry; no public retry/admin endpoint."""

import argparse

from sqlalchemy import select

from aevyra_api.commercial.fulfillment import SynchronousFulfillment
from aevyra_api.commercial.models import Order
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.database import DependencyChecks
from aevyra_api.logging import configure_logging
from aevyra_api.routes.scoring import registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry a paid development order explicitly")
    parser.add_argument("public_order_id")
    args = parser.parse_args()
    config = Settings()
    if config.api_environment == "production":
        parser.error("Development retries are disabled in production")
    configure_logging(config.log_level)
    checks = DependencyChecks(config)
    try:
        with checks.sessions() as session:
            order = session.scalar(
                select(Order).where(Order.public_order_id == args.public_order_id)
            )
            if order is None:
                raise DomainError("Order not found", 404)
            order_id = order.id
        SynchronousFulfillment(checks.sessions, registry, production=False).fulfill(
            order_id, retry_failed=True
        )
    finally:
        checks.close()


if __name__ == "__main__":
    main()
