from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from aevyra_api.commercial.events import PaymentEventProcessor
from aevyra_api.commercial.fulfillment import SynchronousFulfillment
from aevyra_api.commercial.models import Analysis, AnalysisResult, PaymentEvent
from aevyra_api.commercial.orders import OrderService
from aevyra_api.config import Settings
from aevyra_api.main import create_app
from aevyra_api.payments.mock import MockPaymentProvider
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.mock import MockScoringEngine
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.integration


@contextmanager
def postgres_services(revision="head"):
    settings = Settings()
    schema = f"aevyra_test_{uuid4().hex}"
    admin = create_engine(
        settings.database_url.get_secret_value(), connect_args={"connect_timeout": 2}
    )
    database = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        created = True
        database = create_engine(
            settings.database_url.get_secret_value(),
            connect_args={"connect_timeout": 2, "options": f"-c search_path={schema}"},
        )
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with database.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
            if revision == "head":
                command.check(config)
        sessions = sessionmaker(database, expire_on_commit=False)
        provider = MockPaymentProvider(b"isolated-postgres-test-key")
        engine = MockScoringEngine()
        fulfillment = SynchronousFulfillment(sessions, EngineRegistry([engine]), production=False)
        orders = OrderService(sessions, provider)
        processor = PaymentEventProcessor(sessions, fulfillment)
        yield sessions, orders, provider, processor
    finally:
        if database is not None:
            database.dispose()
        if created:
            # Only the exact randomly generated test namespace can be removed.
            assert schema.startswith("aevyra_test_") and len(schema) == 44
            with admin.begin() as connection:
                connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_postgres_http_flow() -> None:
    with postgres_services() as (sessions, orders, provider, processor):
        app = create_app(Settings(api_environment="test", _env_file=None))
        with TestClient(app) as client:
            app.state.sessions = sessions
            app.state.orders = orders
            app.state.mock_provider = provider
            app.state.payment_events = processor
            order = client.post(
                "/api/v1/orders", json={"product_slug": "aevyra-test-analysis"}
            ).json()
            payment = client.post(
                f"/api/v1/orders/{order['public_order_id']}/payments", json={}
            ).json()
            completed = client.post(
                f"/api/v1/dev/payments/{payment['payment_id']}/simulate-success", json={}
            )
            assert completed.status_code == 200
            assert completed.json()["status"] == "COMPLETED"
            result = client.get(f"/api/v1/analyses/{completed.json()['analysis_id']}/result")
            assert result.json()["metadata"]["synthetic"] is True


def test_postgres_concurrent_duplicate_delivery() -> None:
    with postgres_services() as (sessions, orders, provider, processor):
        calls = []

        class CountingMock(MockScoringEngine):
            def predict(self, prepared: bytes) -> float:
                calls.append(prepared)
                return super().predict(prepared)

        processor.fulfillment = SynchronousFulfillment(
            sessions, EngineRegistry([CountingMock()]), production=False
        )
        order = orders.create("aevyra-test-analysis")
        payment = orders.create_payment(order.public_order_id)
        notification = provider.success_event(orders.payment_details(payment.payment_id))
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(processor.process, [notification] * 8))
        assert responses == [order.public_order_id] * 8
        assert len(calls) == 1
        assert orders.get(order.public_order_id).status == "COMPLETED"
        with sessions() as session:
            for model in (PaymentEvent, Analysis, AnalysisResult):
                assert session.scalar(select(func.count()).select_from(model)) == 1
