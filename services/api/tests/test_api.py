from collections.abc import Iterator
from typing import cast

import pytest
from aevyra_api.config import Settings
from aevyra_api.main import create_app
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeChecks:
    def __init__(self, database_ok: bool = True, redis_ok: bool = True) -> None:
        self.database_ok = database_ok
        self.redis_ok = redis_ok

    def database(self) -> None:
        if not self.database_ok:
            raise ConnectionError("secret must not appear in HTTP response")

    def cache(self) -> None:
        if not self.redis_ok:
            raise ConnectionError("secret must not appear in HTTP response")


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(Settings(api_environment="test", _env_file=None))
    with TestClient(app) as client:
        app.state.checks = FakeChecks()
        yield client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aevyra-api"}
    assert response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "database_ok,redis_ok", [(True, True), (False, True), (True, False), (False, False)]
)
def test_readiness(client: TestClient, database_ok: bool, redis_ok: bool) -> None:
    cast(FastAPI, client.app).state.checks = FakeChecks(database_ok, redis_ok)
    response = client.get("/ready")
    assert response.status_code == (200 if database_ok and redis_ok else 503)
    assert response.json()["dependencies"] == {
        "database": "ok" if database_ok else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
    }
    assert "secret" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_engine_registry_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/scoring-engines")
    assert response.status_code == 200
    engine = response.json()["engines"][0]
    assert engine["slug"] == "mock"
    assert engine["synthetic"] is True
    assert engine["production_enabled"] is False


def test_cors(client: TestClient) -> None:
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "Access-Control-Allow-Origin" not in denied.headers


def test_production_requires_credentials() -> None:
    with pytest.raises(ValueError, match="explicit database credentials"):
        Settings(api_environment="production", _env_file=None)


def test_exception_response_is_safe() -> None:
    app = create_app(Settings(api_environment="test", _env_file=None))

    @app.get("/failure")
    def failure() -> None:
        raise RuntimeError("private failure details")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "private" not in response.text
