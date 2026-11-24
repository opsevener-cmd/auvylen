"""Free photo check: consent, limits, spend cap and strict parsing, with a fake Gemini."""

import base64
import json
from decimal import Decimal
from io import BytesIO

import pytest
from aevyra_api.photo_check.gemini import (
    ENDPOINT,
    GeminiPhotoQuality,
    ProviderError,
    api_key_problem,
    parse_response,
    urllib_transport,
)
from aevyra_api.photo_check.models import PhotoCheckAnalysis, PhotoCheckBudgetDay
from aevyra_api.photo_check.service import PhotoCheckService, micro_usd, ranked_photos
from aevyra_contracts.photo_check import CONSENT_VERSION
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select
from test_credits import credits as credits
from test_credits import csrf_headers, register

BASE = "/api/v1/photo-check"
# Dummy key in the current "AQ." format (dotted, 53 characters). Never a real key.
TEST_KEY = "AQ.Ab8RN6-test-only-dummy-key-not-real.0123456789abcd"
CONSENT = {"consent_version": CONSENT_VERSION, "adult_confirmed": True, "processing_accepted": True}


def jpeg(size=(400, 500)):
    output = BytesIO()
    Image.new("RGB", size, (180, 140, 120)).save(output, format="JPEG")
    return base64.b64encode(output.getvalue()).decode()


def photo_json(index, refusal=None, base=6):
    scores = {
        name: None if refusal else base + offset
        for offset, name in enumerate(
            ("lighting", "sharpness", "framing", "expression", "eye_contact", "background")
        )
    }
    scores = {k: (min(v, 10) if v else v) for k, v in scores.items()}
    return {
        "index": index,
        "refusal_reason": refusal,
        **scores,
        "tips": [] if refusal else ["Face the window"],
    }


def gemini_reply(photos, prompt_tokens=2000, output_tokens=300, thoughts=40, finish="STOP"):
    return json.dumps(
        {
            "candidates": [
                {
                    "finishReason": finish,
                    "content": {"parts": [{"text": json.dumps({"photos": photos})}]},
                }
            ],
            "usageMetadata": {
                "promptTokenCount": prompt_tokens,
                "candidatesTokenCount": output_tokens,
                "thoughtsTokenCount": thoughts,
            },
        }
    ).encode()


class FakeTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, json.loads(body)))
        return self.replies.pop(0)


def configure(fixture, transport, **overrides):
    settings = fixture.client.app.state.settings
    settings.free_hook_enabled = True
    settings.gemini_api_key = SecretStr(TEST_KEY)
    settings.free_hook_paid_tier_confirmed = True
    for name, value in overrides.items():
        setattr(settings, name, value)
    fixture.client.app.state.photo_check_provider = lambda s: GeminiPhotoQuality(
        TEST_KEY, s.free_hook_model, transport=transport
    )
    return settings


def submit(fixture, count=1, language="en"):
    return fixture.client.post(
        BASE + "/analyses",
        json={"photos": [jpeg() for _ in range(count)], "language": language},
        headers=csrf_headers(fixture.client),
    )


def accept(fixture):
    response = fixture.client.post(
        BASE + "/consent", json=CONSENT, headers=csrf_headers(fixture.client)
    )
    assert response.status_code == 200, response.text


def test_unavailable_until_enabled_keyed_and_paid_tier_confirmed(credits):
    assert credits.client.get(BASE + "/status").status_code == 401
    register(credits.client)
    status = credits.client.get(BASE + "/status").json()
    assert status["available"] is False and status["reason"] == "disabled"
    assert status["consent_required"] is True and status["daily_limit"] == 30
    settings = credits.client.app.state.settings
    settings.free_hook_enabled = True
    assert credits.client.get(BASE + "/status").json()["reason"] == "not_configured"
    settings.gemini_api_key = SecretStr(TEST_KEY)
    assert credits.client.get(BASE + "/status").json()["reason"] == "paid_tier_unconfirmed"
    accept(credits)
    assert submit(credits).json()["detail"] == "photo_check_unavailable"
    settings.free_hook_paid_tier_confirmed = True
    status = credits.client.get(BASE + "/status").json()
    assert status["available"] is True and status["consent_required"] is False


def test_consent_is_required_and_validated(credits):
    register(credits.client)
    configure(credits, FakeTransport([]))
    response = submit(credits)
    assert (
        response.status_code == 403 and response.json()["detail"] == "photo_check_consent_required"
    )
    bad = {**CONSENT, "adult_confirmed": False}
    response = credits.client.post(
        BASE + "/consent", json=bad, headers=csrf_headers(credits.client)
    )
    assert response.status_code == 422
    accept(credits)
    accept(credits)  # Idempotent.


def test_ranks_photos_records_cost_and_sends_a_strict_request(credits):
    register(credits.client)
    transport = FakeTransport(
        [
            (
                200,
                gemini_reply(
                    [photo_json(0, base=4), photo_json(1, base=7), photo_json(2, "no_person")]
                ),
            )
        ]
    )
    configure(credits, transport)
    accept(credits)
    response = submit(credits, 3, "zh-CN")
    assert response.status_code == 200, response.text
    result = response.json()
    photos = {p["index"]: p for p in result["photos"]}
    assert photos[1]["rank"] == 1 and photos[0]["rank"] == 2
    assert photos[2] == {**photos[2], "usable": False, "rank": None, "scores": None, "tips": []}
    # Plain mean of the six criteria: 7..12 capped at 10 -> (7+8+9+10+10+10)/6.
    assert photos[1]["raw_score"] == pytest.approx(54 / 6)
    assert photos[1]["display_score"] == 9.0
    assert result["used_today"] == 1 and result["engine"] == "gemini-photo-quality"
    url, headers, body = transport.calls[0]
    assert url == ENDPOINT.format(model="gemini-3.5-flash-lite")
    assert headers["x-goog-api-key"] == TEST_KEY
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json" and config["temperature"] == 0
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert config["mediaResolution"] == "MEDIA_RESOLUTION_MEDIUM"
    assert "Simplified Chinese" in body["systemInstruction"]["parts"][0]["text"]
    images = [p for p in body["contents"][0]["parts"] if "inline_data" in p]
    assert len(images) == 3
    with credits.sessions() as session:
        row = session.scalars(select(PhotoCheckAnalysis)).one()
        budget = session.scalars(select(PhotoCheckBudgetDay)).one()
    # 2000 input tokens at $0.30/M = 600 micro-USD; 340 output tokens at $2.50/M = 850.
    assert (row.status, row.cost_micro_usd, row.input_tokens, row.output_tokens) == (
        "COMPLETED",
        1450,
        2000,
        340,
    )
    assert (budget.spent_micro_usd, budget.reserved_micro_usd) == (1450, 0)
    assert row.result is not None and "photos" in row.result


def test_never_sends_or_stores_more_than_five_or_undecodable_photos(credits):
    register(credits.client)
    transport = FakeTransport([])
    configure(credits, transport)
    accept(credits)
    assert submit(credits, 6).status_code == 422
    response = credits.client.post(
        BASE + "/analyses",
        json={"photos": [base64.b64encode(b"not an image").decode()]},
        headers=csrf_headers(credits.client),
    )
    assert response.status_code == 422 and response.json()["detail"] == "photo_check_invalid_photos"
    assert transport.calls == []


def test_daily_user_limit_counts_only_successful_or_in_flight_checks(credits):
    register(credits.client)
    replies = [
        (503, b""),
        (200, gemini_reply([photo_json(0)])),
        (200, gemini_reply([photo_json(0)])),
    ]
    configure(credits, FakeTransport(replies), free_hook_user_daily_limit=2)
    accept(credits)
    failed = submit(credits)
    assert failed.status_code == 503 and failed.json()["detail"] == "photo_check_provider_failed"
    assert submit(credits).status_code == 200
    assert submit(credits).status_code == 200
    limited = submit(credits)
    assert limited.status_code == 429 and limited.json()["detail"] == "photo_check_daily_limit"
    assert credits.client.get(BASE + "/status").json()["used_today"] == 2


def test_global_budget_pauses_the_hook_before_it_can_be_exceeded(credits):
    register(credits.client)
    transport = FakeTransport([(200, gemini_reply([photo_json(0)]))])
    # A full five-photo reservation is 900+3500 input and 1300 output tokens: 4570 micro-USD.
    configure(credits, transport, free_hook_daily_budget_usd=Decimal("0.006"))
    accept(credits)
    assert submit(credits).status_code == 200
    status = credits.client.get(BASE + "/status").json()
    assert status["available"] is False and status["reason"] == "paused"
    paused = submit(credits)
    assert paused.status_code == 503 and paused.json()["detail"] == "photo_check_paused"
    assert len(transport.calls) == 1
    with credits.sessions() as session:
        budget = session.scalars(select(PhotoCheckBudgetDay)).one()
    assert budget.paused_at is not None and budget.reserved_micro_usd == 0


def test_abandoned_reservations_are_charged_conservatively(credits):
    user = register(credits.client)
    configure(credits, FakeTransport([(200, gemini_reply([photo_json(0)]))]))
    accept(credits)
    service = PhotoCheckService(credits.sessions, credits.client.app.state.settings)
    with credits.sessions.begin() as session:
        from aevyra_api.credits.models import User

        owner = session.scalars(
            select(User).where(User.public_user_id == user["public_user_id"])
        ).one()
        day = service.today()
        session.add(PhotoCheckBudgetDay(day=day, spent_micro_usd=0, reserved_micro_usd=999))
        from datetime import timedelta

        from aevyra_api.commercial.models import now

        session.add(
            PhotoCheckAnalysis(
                user_id=owner.id,
                day=day,
                status="RESERVED",
                photo_count=1,
                language="en",
                model="m",
                prompt_version="p",
                consent_version=CONSENT_VERSION,
                reserved_micro_usd=999,
                created_at=now() - timedelta(hours=1),
            )
        )
    assert submit(credits).status_code == 200
    with credits.sessions() as session:
        stale = session.scalars(
            select(PhotoCheckAnalysis).where(PhotoCheckAnalysis.model == "m")
        ).one()
        budget = session.get(PhotoCheckBudgetDay, day)
    assert (stale.status, stale.failure_reason, stale.cost_micro_usd) == (
        "FAILED",
        "abandoned",
        999,
    )
    assert budget.reserved_micro_usd == 0 and budget.spent_micro_usd > 999


def test_blocked_and_invalid_responses_never_become_results():
    usage_reply = gemini_reply([photo_json(0)], finish="SAFETY")
    with pytest.raises(ProviderError) as blocked:
        parse_response(usage_reply, 1)
    assert blocked.value.reason == "blocked" and blocked.value.usage is not None
    with pytest.raises(ProviderError, match="invalid_response"):
        parse_response(gemini_reply([photo_json(1)]), 1)  # Wrong index.
    missing_score = {**photo_json(0), "sharpness": None}
    with pytest.raises(ProviderError, match="invalid_response"):
        parse_response(gemini_reply([missing_score]), 1)
    out_of_range = {**photo_json(0), "lighting": 11}
    with pytest.raises(ProviderError, match="invalid_response"):
        parse_response(gemini_reply([out_of_range]), 1)
    with pytest.raises(ProviderError, match="invalid_response"):
        parse_response(b"not json", 1)


def test_tips_are_trimmed_and_the_overall_score_is_the_mean():
    photo = parse_response(
        gemini_reply([{**photo_json(0), "tips": ["  a" * 100, "b", "c"]}]), 1
    ).photos
    view = ranked_photos(photo)[0]
    assert len(view.tips) == 2 and len(view.tips[0]) <= 120
    assert view.raw_score == pytest.approx((6 + 7 + 8 + 9 + 10 + 10) / 6)


def test_costs_round_up_in_integer_micro_usd():
    assert micro_usd(1, Decimal("0.30")) == 1
    assert micro_usd(1_000_000, Decimal("2.50")) == 2_500_000
    assert micro_usd(3333, Decimal("0.30")) == 1000


def test_production_policy_gate_requires_paid_tier_confirmation(credits):
    settings = credits.client.app.state.settings
    settings.free_hook_enabled = True
    settings.gemini_api_key = SecretStr(TEST_KEY)
    settings.api_environment = "production"
    service = PhotoCheckService(credits.sessions, settings)
    assert service.configuration() == "paid_tier_unconfirmed"
    settings.free_hook_paid_tier_confirmed = True
    assert service.configuration() == "ready"
    assert service.metadata().commercial_allowed is True


# --- API key format (regression: UnicodeEncodeError on the first real check) -------------


def test_aq_auth_keys_are_sent_intact_in_the_header_by_the_real_http_client():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    assert len(TEST_KEY) == 53 and "." in TEST_KEY and api_key_problem(TEST_KEY) is None
    assert api_key_problem("AIza" + "B" * 35) is None  # Classic keys still work.
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["key"] = self.headers.get("x-goog-api-key")
            seen["authorization"] = self.headers.get("authorization")
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(gemini_reply([photo_json(0)]))

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        local = f"http://127.0.0.1:{server.server_port}"

        def transport(url, headers, body, timeout):
            # Same client and headers; only the host is swapped for the local server.
            assert url.startswith("https://generativelanguage.googleapis.com/v1beta/models/")
            return urllib_transport(local + url.split(".com", 1)[1], headers, body, timeout)

        provider = GeminiPhotoQuality(TEST_KEY, "gemini-3.5-flash-lite", transport=transport)
        assessment = provider.assess([b"jpeg"], "en")
    finally:
        server.shutdown()
    assert seen == {
        "path": "/v1beta/models/gemini-3.5-flash-lite:generateContent",
        "key": TEST_KEY,
        "authorization": None,
    }
    assert assessment.photos[0].lighting == 6


MALFORMED_KEYS = {
    "non_ascii_character": [
        "\u201c" + TEST_KEY + "\u201d",  # Curly quotes, e.g. pasted from a document.
        TEST_KEY + "\u200b",  # Zero-width space.
        TEST_KEY[:30] + "\u2026",  # Truncated display copy ending in an ellipsis.
        TEST_KEY + "\u00a0",  # Non-breaking space: sent, then rejected by Google.
    ],
    "quote_character": ['"' + TEST_KEY + '"' + "x"],
    "whitespace": ["AQ.first-half-of-key " + "second-half-of-key"],
    "unexpected_length": ["AQ.short"],
}


@pytest.mark.parametrize(
    ("problem", "key"), [(p, k) for p, keys in MALFORMED_KEYS.items() for k in keys]
)
def test_malformed_keys_are_reported_and_never_reach_the_http_client(problem, key):
    assert api_key_problem(key) == problem
    with pytest.raises(ValueError, match=problem):
        GeminiPhotoQuality(key, "gemini-3.5-flash-lite")


def test_the_real_http_client_cannot_send_non_ascii_keys():
    # Documents the root cause: http.client encodes header values as Latin-1.
    with pytest.raises(UnicodeEncodeError):
        urllib_transport("http://127.0.0.1:9/", {"x-goog-api-key": TEST_KEY + "\u200b"}, b"{}", 1)


def test_a_malformed_configured_key_disables_the_check_instead_of_crashing(credits, caplog):
    register(credits.client)
    transport = FakeTransport([])
    configure(credits, transport)
    credits.client.app.state.settings.gemini_api_key = SecretStr("\u201c" + TEST_KEY + "\u201d")
    status = credits.client.get(BASE + "/status").json()
    assert status["available"] is False and status["reason"] == "not_configured"
    accept_response = credits.client.post(
        BASE + "/consent", json=CONSENT, headers=csrf_headers(credits.client)
    )
    assert accept_response.status_code == 200
    response = submit(credits)
    assert response.status_code == 503 and response.json()["detail"] == "photo_check_unavailable"
    assert transport.calls == []
    events = [r for r in caplog.records if r.getMessage() == "photo_check_api_key_invalid"]
    assert events and events[0].error_type == "non_ascii_character"
    assert TEST_KEY not in caplog.text and TEST_KEY[3:20] not in caplog.text


@pytest.mark.parametrize(
    "raw", [TEST_KEY + "\r", "  " + TEST_KEY + "\n", TEST_KEY + "\r\n", TEST_KEY + "\u00a0"]
)
def test_settings_trim_surrounding_whitespace_and_crlf(raw):
    from aevyra_api.config import Settings

    settings = Settings(api_environment="test", gemini_api_key=raw, _env_file=None)
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == TEST_KEY
    assert (
        Settings(api_environment="test", gemini_api_key=" \r\n", _env_file=None).gemini_api_key
        is None
    )


def test_deploy_doc_snippet_accepts_aq_keys_and_rejects_pasted_artefacts(tmp_path):
    import os
    import re as regex
    import subprocess
    import sys
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[3] / "docs" / "photo-check.md").read_text()
    snippet = regex.search(r"python3 - \.env\.production <<'PY'\n(.*?)\nPY", doc, regex.S).group(1)
    script = tmp_path / "snippet.py"
    script.write_text(snippet)

    def run(key):
        env_file = tmp_path / "env"
        env_file.write_text("FREE_HOOK_ENABLED=false\nGEMINI_API_KEY=\n")
        result = subprocess.run(
            [sys.executable, "-I", str(script), str(env_file)],
            env={**os.environ, "GEMINI_KEY_INPUT": key},
            capture_output=True,
            text=True,
        )
        return result, env_file.read_text()

    result, written = run(TEST_KEY + "\n")
    assert result.returncode == 0, result.stderr
    assert f"GEMINI_API_KEY={TEST_KEY}\n" in written and "FREE_HOOK_ENABLED=true" in written
    assert TEST_KEY not in result.stdout + result.stderr
    # Surrounding whitespace, even a non-breaking space, is trimmed: the clean key is kept.
    result, written = run(TEST_KEY + "\u00a0")
    assert result.returncode == 0 and f"GEMINI_API_KEY={TEST_KEY}\n" in written
    inner = [k for k in MALFORMED_KEYS["non_ascii_character"] if not k.endswith("\u00a0")]
    for bad in inner + MALFORMED_KEYS["whitespace"]:
        result, written = run(bad)
        assert result.returncode != 0 and f"GEMINI_API_KEY={bad}" not in written
        assert bad not in result.stdout + result.stderr
