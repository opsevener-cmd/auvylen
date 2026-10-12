import json
import logging
from uuid import uuid4

import pytest
from aevyra_api.config import Settings
from aevyra_api.logging import JsonFormatter
from aevyra_api.main import create_app
from fastapi.testclient import TestClient


def deployment_settings(**overrides):
    values = {
        "api_environment": "production",
        "database_url": "postgresql+psycopg://aevyra:testing-only-long-password@postgres/aevyra",
        "redis_url": "redis://redis:6379/0",
        "cors_origins": [],
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_url": "postgresql+psycopg://aevyra:short@postgres/aevyra"},
        {"database_url": "sqlite:///temporary.db"},
        {"redis_url": ""},
        {"cors_origins": ["*"]},
        {"cors_origins": ["http://example.com"]},
        {"log_level": "DEBUG"},
        {"payment_provider": "wechat"},
    ],
)
def test_deployment_rejects_unsafe_configuration(overrides):
    with pytest.raises(ValueError):
        deployment_settings(**overrides)


def test_explicit_connections_required():
    with pytest.raises(ValueError, match="explicit Redis"):
        Settings(
            api_environment="production",
            database_url="postgresql+psycopg://u:testing-only-long-password@db/a",
            _env_file=None,
        )


def test_app_env_takes_precedence(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_ENVIRONMENT", "development")
    assert deployment_settings().api_environment == "production"


def test_staging_configuration():
    assert deployment_settings(api_environment="staging").api_environment == "staging"


def test_production_routes_fail_closed():
    app = create_app(deployment_settings())
    assert app.debug is False
    with TestClient(app) as client:
        for path in (
            "/docs",
            "/openapi.json",
            "/api/v1/products",
            f"/api/v1/analyses/{uuid4()}/result",
        ):
            assert client.get(path).status_code == 404
        for path, body in (
            ("/api/v1/orders", {"product_slug": "aevyra-test-analysis"}),
            ("/api/v1/orders/any/payments", {}),
            (f"/api/v1/dev/payments/{uuid4()}/simulate-success", {}),
        ):
            assert client.post(path, json=body).status_code == 404
        assert client.get("/health").status_code == 200


def test_staging_retains_mock_flow(commerce):
    commerce.client.app.state.settings = deployment_settings(api_environment="staging")
    client = commerce.client
    order = client.post("/api/v1/orders", json={"product_slug": "aevyra-test-analysis"}).json()
    payment = client.post(f"/api/v1/orders/{order['public_order_id']}/payments", json={}).json()
    response = client.post(
        f"/api/v1/dev/payments/{payment['payment_id']}/simulate-success", json={}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_server_exception_log_does_not_expose_exception_text():
    error = RuntimeError("private-credential")
    record = logging.LogRecord(
        "uvicorn.error", logging.ERROR, "", 0, "private-credential", (), (RuntimeError, error, None)
    )
    output = JsonFormatter().format(record)
    assert "private-credential" not in output
    assert json.loads(output)["error_type"] == "RuntimeError"
    assert json.loads(output)["service"] == "aevyra-api"
