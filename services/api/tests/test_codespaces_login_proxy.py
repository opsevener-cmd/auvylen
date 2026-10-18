"""Built Next.js -> real FastAPI auth, with simulated GitHub forwarding headers.

Run after `npm run build`: uv run pytest --integration
services/api/tests/test_codespaces_login_proxy.py. Only ephemeral loopback listeners
and the existing migrated in-memory commerce fixture are used; no retained data.
"""

import json
import os
import socket
import subprocess
import threading
import time
from datetime import timedelta
from pathlib import Path

import httpx2
import pytest
import uvicorn
from aevyra_api.accounts import COOKIE, CSRF_COOKIE, AccountService
from aevyra_api.commercial.models import now
from aevyra_api.config import Settings
from aevyra_api.credits.models import AccountSession
from aevyra_api.main import create_app
from sqlalchemy import update
from test_credits import PASSWORD, TestLimiter

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]
NAME = "opulent-umbrella-6v5456gw9jx5hrg69"
HOST = f"{NAME}-3000.app.github.dev"
ORIGIN = f"https://{HOST}"
FORWARDED = {
    "host": HOST,
    "x-forwarded-host": HOST,
    "origin": "http://localhost:3000",
    "sec-fetch-site": "same-origin",
    "referer": f"{ORIGIN}/account",
}
CREDENTIALS = {"login_identifier": "proxy-test-user", "password": PASSWORD}


@pytest.fixture
def proxy(commerce, tmp_path):
    assert (ROOT / "apps/web/.next/BUILD_ID").exists(), "Run npm run build first"
    settings = Settings(
        api_environment="test", cors_origins=[ORIGIN], session_cookie_secure=True, _env_file=None
    )
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = commerce.sessions
    app.state.rate_limiter = TestLimiter()
    AccountService(commerce.sessions, settings).register(
        **{
            "identifier": CREDENTIALS["login_identifier"],
            "password": PASSWORD,
        }
    )
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    api_port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, lifespan="off", access_log=False, log_level="error")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        web_port = reservation.getsockname()[1]
    env = dict(
        os.environ,
        APP_ENV="staging",
        CODESPACES="true",
        CODESPACE_NAME=NAME,
        GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN="app.github.dev",
        CORS_ORIGINS=json.dumps([ORIGIN]),
        API_URL=f"http://127.0.0.1:{api_port}",
        NEXT_TELEMETRY_DISABLED="1",
    )
    process = None
    try:
        with (tmp_path / "next.log").open("w") as log:
            process = subprocess.Popen(
                [
                    "node",
                    str(ROOT / "node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=ROOT / "apps/web",
                env=env,
                stdout=log,
                stderr=log,
            )
            with httpx2.Client(base_url=f"http://127.0.0.1:{web_port}", trust_env=False) as client:
                deadline = time.monotonic() + 30
                while True:
                    assert process.poll() is None, "Next.js exited before readiness"
                    try:
                        if client.get("/api/v1/auth/csrf").status_code == 200:
                            break
                    except httpx2.TransportError:
                        pass  # The ephemeral test listeners are still starting.
                    assert time.monotonic() < deadline, "Proxy readiness timed out"
                    time.sleep(0.1)
                yield client, commerce.sessions, api_port
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


def csrf(client):
    response = client.get("/api/v1/auth/csrf", headers={"host": HOST})
    assert response.status_code == 200
    cookie = response.cookies[CSRF_COOKIE]
    # Simulate the trusted forwarder's HTTPS->loopback hop. Do not disable Secure
    # cookies in the app: explicitly relay the browser's cookie in this test only.
    return {
        **FORWARDED,
        "cookie": f"{CSRF_COOKIE}={cookie}",
        "x-csrf-token": response.json()["csrf_token"],
    }


@pytest.mark.parametrize("origin", ["http://localhost:3000", ORIGIN])
def test_login_session_logout_and_expiry_through_codespaces_proxy(proxy, origin):
    client, sessions, _ = proxy
    headers = {**csrf(client), "origin": origin}
    bad_password = client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={**CREDENTIALS, "password": "invalid-test-password"},
    )
    assert bad_password.status_code == 401
    response = client.post("/api/v1/auth/login", headers=headers, json=CREDENTIALS)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith(COOKIE + "="))
    for flag in ("Secure", "HttpOnly", "SameSite=lax", "Max-Age="):
        assert flag in session_cookie
    assert len(cookies) == 2  # Session creation AND pre-login cookie deletion survive the proxy.
    assert response.headers["cache-control"] == "private, no-store"
    authenticated = {
        **FORWARDED,
        "cookie": f"{COOKIE}={response.cookies[COOKIE]}",
        "x-csrf-token": response.json()["csrf_token"],
    }
    assert client.get("/api/v1/auth/me", headers=authenticated).status_code == 200
    assert client.get("/api/v1/owner/overview", headers=authenticated).status_code == 403
    assert client.get("/api/v1/auth/me", headers={"cookie": f"{COOKIE}=forged"}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=authenticated, json={}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=authenticated).status_code == 401
    again = client.post("/api/v1/auth/login", headers=csrf(client), json=CREDENTIALS)
    assert again.status_code == 200
    with sessions.begin() as session:
        session.execute(update(AccountSession).values(expires_at=now() - timedelta(seconds=1)))
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={
                "cookie": f"{COOKIE}={again.cookies[COOKIE]}",
            },
        ).status_code
        == 401
    )


def test_forged_missing_and_unauthorized_origin_rejected_before_login(proxy):
    client, _, _ = proxy
    valid = csrf(client)
    attacks = [
        {"origin": None},
        {"origin": "null"},
        {"origin": "https://attacker.example"},
        {"origin": "https://other-space-3000.app.github.dev"},
        {"origin": "http://localhost:3001"},
        {"origin": "http://127.0.0.1:3000"},
        {"host": "localhost:3000"},
        {"host": f"{HOST}.evil.test"},
        {"x-forwarded-host": "attacker.example"},
        {"x-forwarded-host": f"{HOST}, attacker.example"},
        {"referer": None},
        {"referer": "https://attacker.example/account"},
        {"sec-fetch-site": None},
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
    ]
    for override in attacks:
        headers = {k: v for k, v in {**valid, **override}.items() if v is not None}
        response = client.post("/api/v1/auth/login", headers=headers, json=CREDENTIALS)
        assert response.status_code == 403, tuple(override)
        assert response.json() == {"detail": "Request origin rejected"}
        assert not response.headers.get_list("set-cookie")


def test_normalization_does_not_bypass_csrf_or_change_fastapi_origin_policy(proxy):
    client, _, api_port = proxy
    valid = csrf(client)
    for override in ({"x-csrf-token": "forged"}, {"x-csrf-token": None}, {"cookie": None}):
        headers = {k: v for k, v in {**valid, **override}.items() if v is not None}
        client.cookies.clear()
        response = client.post("/api/v1/auth/login", headers=headers, json=CREDENTIALS)
        assert response.status_code == 403
        assert response.json() == {"detail": "CSRF validation failed"}
    with httpx2.Client(base_url=f"http://127.0.0.1:{api_port}", trust_env=False) as backend:
        preflight = backend.options(
            "/api/v1/auth/login",
            headers={
                "origin": ORIGIN,
                "access-control-request-method": "POST",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == ORIGIN
        for origin in ("http://localhost:3000", "https://attacker.example"):
            response = backend.post(
                "/api/v1/auth/login", headers={**valid, "origin": origin}, json=CREDENTIALS
            )
            assert response.status_code == 403
            assert response.json() == {"detail": "Request origin rejected"}
