from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from aevyra_api.commercial.events import PaymentEventProcessor
from aevyra_api.commercial.fulfillment import SynchronousFulfillment
from aevyra_api.commercial.orders import OrderService
from aevyra_api.config import Settings
from aevyra_api.main import create_app
from aevyra_api.payments.mock import MockPaymentProvider
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.mock import MockScoringEngine
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


class CountingEngine(MockScoringEngine):
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def predict(self, prepared: bytes) -> float:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sensitive details must not be exposed")
        return super().predict(prepared)


@dataclass
class CommercialFixture:
    client: TestClient
    sessions: sessionmaker[Session]
    orders: OrderService
    events: PaymentEventProcessor
    fulfillment: SynchronousFulfillment
    provider: MockPaymentProvider
    engine: CountingEngine


@pytest.fixture
def commerce() -> Iterator[CommercialFixture]:
    database = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(database, "connect")
    def foreign_keys(connection, record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with database.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.check(config)
    sessions = sessionmaker(database, expire_on_commit=False)
    engine = CountingEngine()
    provider = MockPaymentProvider(b"local-test-signature-key")
    fulfillment = SynchronousFulfillment(sessions, EngineRegistry([engine]), production=False)
    orders = OrderService(sessions, provider)
    processor = PaymentEventProcessor(sessions, fulfillment)
    app = create_app(Settings(api_environment="test", _env_file=None))
    try:
        with TestClient(app) as client:
            app.state.sessions = sessions
            app.state.orders = orders
            app.state.payment_events = processor
            app.state.mock_provider = provider
            yield CommercialFixture(
                client, sessions, orders, processor, fulfillment, provider, engine
            )
    finally:
        database.dispose()
