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
    "host": "localhost:3000",
    "x-forwarded-host": HOST,
    "x-forwarded-proto": "https",
    "origin": "http://localhost:3000",
    "sec-fetch-site": "same-origin",
    "referer": f"{ORIGIN}/account",
}
CREDENTIALS = {"login_identifier": "proxy-test-user", "password": PASSWORD}


@pytest.fixture
def proxy(commerce, tmp_path, request):
    assert (ROOT / "apps/web/.next/BUILD_ID").exists(), "Run npm run build first"
    extra = {}
    if getattr(request, "param", False):
        extra = dict(
            research_mode=True,
            native_preview_enabled=True,
            native_preview_checkpoint=tmp_path / "fixture-checkpoint",
            native_preview_manifest_sha256="a" * 64,
            native_preview_review_reference="transport-fixture-only-not-model-evidence",
            private_upload_root=tmp_path / "private",
        )
    settings = Settings(
        api_environment="test",
        cors_origins=[ORIGIN],
        session_cookie_secure=True,
        _env_file=None,
        **extra,
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


@pytest.mark.parametrize(
    "host,origin", [("localhost:3000", "http://localhost:3000"), (HOST, ORIGIN)]
)
def test_login_session_logout_and_expiry_through_codespaces_proxy(proxy, host, origin):
    client, sessions, _ = proxy
    headers = {**csrf(client), "host": host, "origin": origin}
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
        {"host": HOST},
        {"host": "localhost:3001"},
        {"host": "127.0.0.1:3000"},
        {"origin": ORIGIN},
        {"host": f"{HOST}.evil.test"},
        {"x-forwarded-host": None},
        {"x-forwarded-host": "attacker.example"},
        {"x-forwarded-host": f"{HOST}, attacker.example"},
        {"x-forwarded-host": f"{HOST}, {HOST}"},
        {"x-forwarded-proto": None},
        {"x-forwarded-proto": "http"},
        {"x-forwarded-proto": "https, http"},
        {"x-forwarded-proto": "https, https"},
        {"referer": None},
        {"referer": "https://attacker.example/account"},
        {"referer": f"{ORIGIN}/account, https://attacker.example/"},
        {"sec-fetch-site": None},
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
        {"host": HOST, "origin": ORIGIN, "x-forwarded-host": "attacker.example"},
        {"host": HOST, "origin": ORIGIN, "x-forwarded-proto": "http"},
        {"host": HOST, "origin": ORIGIN, "referer": "https://attacker.example/account"},
        {"host": HOST, "origin": ORIGIN, "sec-fetch-site": "cross-site"},
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


@pytest.mark.parametrize("proxy", [True], indirect=True)
def test_native_preview_four_mib_real_proxy_queue_and_retention(proxy, tmp_path):
    """Real built proxy/API/queue; child output is an explicitly withheld transport fixture.

    No checkpoint, human portrait or numerical attractiveness prediction is fabricated.
    """
    from io import BytesIO
    from types import SimpleNamespace
    from unittest.mock import patch
    from urllib.parse import quote
    from uuid import UUID, uuid4

    from aevyra_api.owner import provision
    from aevyra_api.research.models import ResearchJob
    from aevyra_api.research.native_preview import NativePreview
    from aevyra_api.research.worker import run_one
    from PIL import Image
    from sqlalchemy import select
    from test_owner import OWNER_PASSWORD

    client, sessions, _ = proxy
    provision(sessions, OWNER_PASSWORD)
    signed = client.post(
        "/api/v1/auth/login",
        headers=csrf(client),
        json={"login_identifier": "owner_god", "password": OWNER_PASSWORD},
    )
    assert signed.status_code == 200
    auth = {
        **FORWARDED,
        "cookie": f"{COOKIE}={signed.cookies[COOKIE]}",
        "x-csrf-token": signed.json()["csrf_token"],
    }
    root = "/api/v1/research/native-preview"
    metadata = quote(
        json.dumps(
            dict(
                idempotency_key=str(uuid4()),
                adult_subject_attested=True,
                single_subject_attested=True,
                authorized_consent=True,
            )
        )
    )
    payload = BytesIO()
    Image.new("RGB", (256, 320), (40, 60, 80)).save(payload, "PNG")
    # Valid PNG plus trailing padding: exercise the exact 4 MiB HTTP boundary.
    data = payload.getvalue().ljust(4 * 1024**2, b"\0")
    headers = {**auth, "Content-Type": "image/png", "X-Upload-Metadata": metadata}
    manifest = SimpleNamespace(
        collection=SimpleNamespace(name="transport-fixture", synthetic=True),
        encoder="transport-fixture",
        created_at=now().isoformat(),
        report={},
    )
    settings = Settings(
        api_environment="test",
        research_mode=True,
        native_preview_enabled=True,
        native_preview_checkpoint=tmp_path / "fixture-checkpoint",
        native_preview_manifest_sha256="a" * 64,
        native_preview_review_reference="transport-fixture-only-not-model-evidence",
        private_upload_root=tmp_path / "private",
        _env_file=None,
    )
    service = NativePreview(sessions, settings)
    with patch.object(NativePreview, "ready", return_value=manifest):
        assert client.get(root + "/status", headers=auth).json()["available"]
        assert (
            client.post(
                root + "/jobs", headers={**headers, "x-csrf-token": "bad"}, content=data
            ).status_code
            == 403
        )
        assert (
            client.post(
                root + "/jobs",
                headers={**headers, "origin": "https://attacker.example"},
                content=data,
            ).status_code
            == 403
        )
        assert client.post(root + "/jobs", headers=headers, content=data + b"x").status_code == 413
        response = client.post(root + "/jobs", headers=headers, content=data)
        assert response.status_code == 202, response.text
        assert response.headers["cache-control"] == "private, no-store"
        job_id = response.json()["id"]
        assert client.post(root + "/jobs", headers=headers, content=data).json()["id"] == job_id
        assert len(client.get(root + "/jobs", headers=auth).json()) == 1
        withheld = dict(
            predicted_rating=None,
            input_check=dict(
                verdict="outside", distance=4.4, caution_above=1.85, outside_above=2.82
            ),
            native_scale=[1, 7],
            manifest_sha256="a" * 64,
            encoder="transport-fixture",
            collection="transport-fixture",
            research_only=True,
            synthetic=False,
            consumer_enabled=False,
            release_failures=["fixture_only"],
            duration_ms=0,
            peak_rss_kib=1,
        )
        with patch(
            "aevyra_api.research.native_preview.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=json.dumps(withheld)),
        ):
            assert run_one(service.queue)
        result = client.get(root + "/jobs/" + job_id, headers=auth).json()
        assert result["status"] == "COMPLETED" and result["result"]["predicted_rating"] is None
        assert not list(service.store.root.rglob("*/*"))
        assert (
            client.post(root + "/jobs/" + job_id + "/delete", headers=auth, json={}).status_code
            == 200
        )
        assert client.get(root + "/jobs/" + job_id, headers=auth).status_code == 404
        assert client.get(root + "/jobs", headers=auth).json() == []
        # Unrelated mutation paths did not inherit the expanded image-body budget.
        assert (
            client.post(
                "/api/v1/auth/login", headers=auth, content=b"x" * (1024**2 + 1)
            ).status_code
            == 413
        )
        with sessions() as session:
            assert (
                session.scalar(select(ResearchJob).where(ResearchJob.id == UUID(job_id))).result
                is None
            )
