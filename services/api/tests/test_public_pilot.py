from uuid import uuid4

import pytest
from aevyra_api.main import create_app
from fastapi.testclient import TestClient
from test_deployment_config import deployment_settings


def pilot_settings(**overrides):
    values = dict(
        api_environment="staging", public_pilot=True, public_base_url="https://pilot.example.test"
    )
    values.update(overrides)
    return deployment_settings(**values)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "http://example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://user:secret@example.com",
        "https://example.com/",
        "https://example.com/path",
        "https://example.com?q=secret",
        "https://example.com#fragment",
        "https://*.example.com",
        "https://example..com",
    ],
)
def test_pilot_rejects_invalid_origin(url):
    with pytest.raises(ValueError):
        pilot_settings(public_base_url=url)


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_pilot_requires_staging(environment):
    with pytest.raises(ValueError, match="requires APP_ENV=staging"):
        pilot_settings(api_environment=environment)


def test_public_origin_drives_cors_and_secure_cookies():
    config = pilot_settings()
    assert config.cors_origins == ["https://pilot.example.test"]
    assert config.session_cookie_secure
    with TestClient(create_app(config), base_url="https://pilot.example.test") as client:
        response = client.get("/api/v1/auth/csrf")
        cookie = response.headers["set-cookie"].lower()
        assert all(attribute in cookie for attribute in ("secure", "httponly", "samesite=lax"))
        token = response.json()["csrf_token"]
        response = client.post(
            "/api/v1/auth/register",
            json={},
            headers={
                "Origin": "https://attacker.example.test",
                "X-CSRF-Token": token,
                "X-Forwarded-Host": "pilot.example.test",
                "X-Forwarded-Proto": "https",
            },
        )
        assert response.status_code == 403
        response = client.post(
            "/api/v1/auth/register",
            json={},
            headers={"Origin": "https://pilot.example.test", "X-CSRF-Token": token},
        )
        assert response.status_code == 422  # Origin/CSRF passed; body is intentionally invalid.
        for path in ("/docs", "/openapi.json", "/api/v1/products"):
            assert client.get(path).status_code == 404
        for path in ("/api/v1/orders", f"/api/v1/dev/payments/{uuid4()}/simulate-success"):
            assert client.post(path, json={}).status_code == 404
        assert client.get("/health").status_code == 200


def test_public_url_without_explicit_pilot_rejected():
    with pytest.raises(ValueError):
        deployment_settings(public_base_url="https://example.com")
