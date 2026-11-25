"""Photo check: consent, quota and Credits, spend cap, appearance, roast and strict parsing,
with a fake Gemini. Never contacts Google."""

import base64
import json
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from aevyra_api.commercial.models import now
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import CreditTransaction, User, Wallet
from aevyra_api.photo_check.consistency import summarize
from aevyra_api.photo_check.gemini import (
    ENDPOINT,
    ROAST_OFF,
    GeminiPhotoQuality,
    ProviderError,
    api_key_problem,
    parse_response,
    urllib_transport,
)
from aevyra_api.photo_check.models import (
    PhotoCheckAnalysis,
    PhotoCheckBudgetDay,
    PhotoCheckConsent,
)
from aevyra_api.photo_check.safety import appearance_lines, roast_lines
from aevyra_api.photo_check.service import (
    PhotoCheckService,
    micro_usd,
    passes_quality_gate,
    ranked_photos,
    week_start,
)
from aevyra_contracts.photo_check import CONSENT_VERSION, QUALITY_GATE, PhotoCheckPhoto
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select
from test_credits import credits as credits
from test_credits import csrf_headers, register

BASE = "/api/v1/photo-check"
# Dummy key in the current "AQ." format (dotted, 53 characters). Never a real key.
TEST_KEY = "AQ.Ab8RN6-test-only-dummy-key-not-real.0123456789abcd"
CONSENT = {"consent_version": CONSENT_VERSION, "adult_confirmed": True, "processing_accepted": True}
CRITERIA = ("lighting", "sharpness", "framing", "expression", "eye_contact", "background")


def jpeg(size=(400, 500)):
    output = BytesIO()
    Image.new("RGB", size, (180, 140, 120)).save(output, format="JPEG")
    return base64.b64encode(output.getvalue()).decode()


def photo_json(index, refusal=None, base=6, band=3, roast=(), vibe=None, scores=None, **appearance):
    if scores is not None:  # Exact six technique scores, in CRITERIA order.
        scores = dict(zip(CRITERIA, scores, strict=True))
    else:
        scores = {
            name: None if refusal else min(base + offset, 10)
            for offset, name in enumerate(CRITERIA)
        }
    return {
        "index": index,
        "refusal_reason": refusal,
        **scores,
        "tips": [] if refusal else ["Face the window"],
        "appearance_strengths": [] if refusal else appearance.get("strengths", ["Warm smile"]),
        "appearance_flattering": []
        if refusal
        else appearance.get("flattering", ["Soft side light"]),
        "appearance_tips": [] if refusal else appearance.get("tips", ["Try a darker jacket"]),
        "band": None if refusal else band,
        "roast_lines": list(roast),
        "vibe": vibe,
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


def ok(**kwargs):
    return (200, gemini_reply([photo_json(0, **kwargs)]))


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


def submit(fixture, count=1, language="en", roast="off", confirmed=True):
    body = {"photos": [jpeg() for _ in range(count)], "language": language, "roast": roast}
    if confirmed:
        body["self_and_adult_confirmed"] = True
    return fixture.client.post(BASE + "/analyses", json=body, headers=csrf_headers(fixture.client))


def accept(fixture):
    response = fixture.client.post(
        BASE + "/consent", json=CONSENT, headers=csrf_headers(fixture.client)
    )
    assert response.status_code == 200, response.text


def status(fixture):
    return fixture.client.get(BASE + "/status").json()


def account(fixture, public_id):
    with fixture.sessions() as session:
        return session.scalars(select(User).where(User.public_user_id == public_id)).one()


def grant(fixture, public_id, amount):
    with fixture.sessions.begin() as session:
        user = session.scalars(select(User).where(User.public_user_id == public_id)).one()
        append_credit(
            session,
            lock_wallet(session, user.id),
            amount=amount,
            kind="TEST_GRANT",
            reference_type="test",
            reference_id="grant",
            key=f"test-grant:{amount}:{now().timestamp()}",
        )


def balance(fixture, public_id):
    with fixture.sessions() as session:
        user = session.scalars(select(User).where(User.public_user_id == public_id)).one()
        return session.scalar(select(Wallet.cached_balance).where(Wallet.user_id == user.id))


def ledger(fixture):
    with fixture.sessions() as session:
        return [
            (t.transaction_type, t.amount)
            for t in session.scalars(
                select(CreditTransaction)
                .where(CreditTransaction.transaction_type.like("PHOTO_CHECK%"))
                .order_by(CreditTransaction.created_at)
            )
        ]


def test_unavailable_until_enabled_keyed_and_paid_tier_confirmed(credits):
    assert credits.client.get(BASE + "/status").status_code == 401
    register(credits.client)
    current = status(credits)
    assert current["available"] is False and current["reason"] == "disabled"
    assert current["consent_required"] is True and current["free_checks_now"] == 4
    assert current["free_signup_remaining"] == 3 and current["next_free_on"] is None
    assert current["credit_cost"] == 1 and current["roast_available"] is False
    settings = credits.client.app.state.settings
    settings.free_hook_enabled = True
    assert status(credits)["reason"] == "not_configured"
    settings.gemini_api_key = SecretStr(TEST_KEY)
    assert status(credits)["reason"] == "paid_tier_unconfirmed"
    accept(credits)
    assert submit(credits).json()["detail"] == "photo_check_unavailable"
    settings.free_hook_paid_tier_confirmed = True
    current = status(credits)
    assert current["available"] is True and current["consent_required"] is False


def test_consent_v2_is_required_and_old_consent_must_be_renewed(credits):
    user = register(credits.client)
    configure(credits, FakeTransport([]))
    with credits.sessions.begin() as session:
        session.add(
            PhotoCheckConsent(
                user_id=account(credits, user["public_user_id"]).id,
                consent_version="gemini-paid-v1",
                adult_confirmed=True,
                processing_accepted=True,
            )
        )
    assert CONSENT_VERSION == "gemini-paid-v2"
    assert status(credits)["consent_required"] is True  # v1 does not cover appearance.
    response = submit(credits)
    assert response.status_code == 403
    assert response.json()["detail"] == "photo_check_consent_required"
    for bad in (
        {**CONSENT, "adult_confirmed": False},
        {**CONSENT, "consent_version": "gemini-paid-v1"},
    ):
        rejected = credits.client.post(
            BASE + "/consent", json=bad, headers=csrf_headers(credits.client)
        )
        assert rejected.status_code == 422
    accept(credits)
    accept(credits)  # Idempotent.
    assert status(credits)["consent_required"] is False


def test_every_upload_must_confirm_own_face_and_18_plus(credits):
    register(credits.client)
    transport = FakeTransport([])
    configure(credits, transport)
    accept(credits)
    response = submit(credits, confirmed=False)
    assert response.status_code == 422
    assert response.json()["detail"] == "photo_check_confirmation_required"
    assert transport.calls == []


def test_ranks_photos_with_appearance_and_records_cost(credits):
    register(credits.client)
    transport = FakeTransport(
        [
            (
                200,
                gemini_reply(
                    [
                        photo_json(0, base=4, band=2),
                        photo_json(1, base=7, band=4),
                        photo_json(2, "no_person"),
                    ]
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
    assert photos[2] == {
        **photos[2],
        "usable": False,
        "rank": None,
        "scores": None,
        "tips": [],
        "appearance": None,
    }
    # Plain mean of the six criteria: 7..12 capped at 10 -> (7+8+9+10+10+10)/6.
    assert photos[1]["raw_score"] == pytest.approx(54 / 6)
    assert photos[1]["display_score"] == 9.0
    assert photos[1]["appearance"] == {
        "strengths": ["Warm smile"],
        "flattering": ["Soft side light"],
        "tips": ["Try a darker jacket"],
        "band": 4,
    }
    assert photos[1]["roast"] is None  # Roast is off unless asked for.
    assert result["engine"] == "gemini-photo-check" and result["funding"] == "free_signup"
    assert result["credits_charged"] == 0 and result["free_checks_now"] == 3
    url, headers, body = transport.calls[0]
    assert url == ENDPOINT.format(model="gemini-3.5-flash-lite")
    assert headers["x-goog-api-key"] == TEST_KEY
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json" and config["temperature"] == 0
    assert isinstance(config["seed"], int)
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert config["mediaResolution"] == "MEDIA_RESOLUTION_MEDIUM"
    prompt = body["systemInstruction"]["parts"][0]["text"]
    assert "Simplified Chinese" in prompt and ROAST_OFF in prompt
    for rule in ("flaw", "cosmetic surgery", "diets", "race, ethnicity", "under 18"):
        assert rule in prompt
    assert len([p for p in body["contents"][0]["parts"] if "inline_data" in p]) == 3
    with credits.sessions() as session:
        row = session.scalars(select(PhotoCheckAnalysis)).one()
        budget = session.scalars(select(PhotoCheckBudgetDay)).one()
    # 2000 input tokens at $0.30/M = 600 micro-USD; 340 output tokens at $2.50/M = 850.
    assert (row.status, row.cost_micro_usd, row.funding, row.roast) == (
        "COMPLETED",
        1450,
        "free_signup",
        "off",
    )
    assert (budget.spent_micro_usd, budget.reserved_micro_usd) == (1450, 0)


@pytest.mark.parametrize(
    ("model_reason", "public_reason"),
    [
        ("multiple_people", "cannot_analyse"),
        ("appears_under_18", "cannot_analyse"),
        ("explicit", "cannot_analyse"),
        ("no_person", "no_person"),
        ("not_a_photo", "not_a_photo"),
    ],
)
def test_refusals_are_neutral_and_carry_no_score_or_band(model_reason, public_reason):
    photos = parse_response(gemini_reply([photo_json(0, model_reason)]), 1).photos
    view = ranked_photos(photos, "spicy")[0]
    assert view.refusal_reason == public_reason
    assert view.usable is False and view.scores is None and view.appearance is None
    assert view.roast is None and view.raw_score is None


def test_free_quota_then_weekly_then_credits_charged_only_on_success(credits):
    user = register(credits.client)
    public = user["public_user_id"]
    replies = [ok(), ok(), (503, b""), ok(), ok(), (503, b""), ok()]
    configure(credits, FakeTransport(replies))
    accept(credits)
    # Three lifetime free checks; a failed check never uses one.
    assert submit(credits).json()["funding"] == "free_signup"
    assert submit(credits).json()["funding"] == "free_signup"
    assert submit(credits).json()["detail"] == "photo_check_provider_failed"
    assert submit(credits).json()["funding"] == "free_signup"
    # Then this week's free check.
    assert status(credits)["free_signup_remaining"] == 0
    weekly = submit(credits).json()
    assert weekly["funding"] == "free_weekly" and weekly["free_checks_now"] == 0
    monday = week_start(date.today()) + timedelta(days=7)
    assert weekly["next_free_on"] == monday.isoformat()
    # Then Credits: refused without a balance, nothing called.
    refused = submit(credits)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "photo_check_insufficient_credits"
    grant(credits, public, 2)
    # A provider failure refunds the debit; a success keeps it.
    assert submit(credits).json()["detail"] == "photo_check_provider_failed"
    assert balance(credits, public) == 2
    paid = submit(credits).json()
    assert paid["funding"] == "credits" and paid["credits_charged"] == 1
    assert balance(credits, public) == 1
    assert ledger(credits) == [
        ("PHOTO_CHECK", -1),
        ("PHOTO_CHECK_REFUND", 1),
        ("PHOTO_CHECK", -1),
    ]
    current = status(credits)
    assert current["credit_balance"] == 1 and current["next_free_on"] == monday.isoformat()


def test_credit_cost_is_configurable(credits):
    user = register(credits.client)
    configure(
        credits,
        FakeTransport([ok()]),
        photo_check_free_signup=0,
        photo_check_free_weekly=0,
        photo_check_credit_cost=3,
    )
    accept(credits)
    grant(credits, user["public_user_id"], 5)
    assert status(credits)["next_free_on"] is None  # No weekly free checks configured.
    assert submit(credits).json()["credits_charged"] == 3
    assert balance(credits, user["public_user_id"]) == 2


def test_owner_is_never_charged(credits):
    from test_owner import owner

    owner(credits)  # Provisions the Owner and signs in.
    configure(credits, FakeTransport([ok()]), photo_check_free_signup=0, photo_check_free_weekly=0)
    accept(credits)
    assert status(credits)["credit_cost"] == 0
    result = submit(credits).json()
    assert result["funding"] == "owner" and result["credits_charged"] == 0
    assert ledger(credits) == []


def test_roast_is_offered_from_the_second_check_and_stays_within_limits(credits):
    register(credits.client)
    roasted = ok(
        roast=[
            "That ceiling light is auditioning for interrogation-room drama.",
            "Your nose is doing a lot here",  # Body: dropped.
        ],
        vibe="hk_film_lead_90s",
    )
    transport = FakeTransport([ok(), roasted])
    configure(credits, transport)
    accept(credits)
    assert status(credits)["roast_available"] is False
    first = submit(credits, roast="spicy").json()
    # The first check stays friendly: roast is switched off and not even requested.
    assert first["photos"][0]["roast"] is None
    assert ROAST_OFF in transport.calls[0][2]["systemInstruction"]["parts"][0]["text"]
    assert status(credits)["roast_available"] is True
    second = submit(credits, roast="spicy").json()
    prompt = transport.calls[1][2]["systemInstruction"]["parts"][0]["text"]
    assert "Roast (spicy)" in prompt and "never meaner" in prompt
    assert "Never compare the person to a real or famous person" in prompt
    assert second["photos"][0]["roast"] == {
        "lines": ["That ceiling light is auditioning for interrogation-room drama."],
        "vibe": "hk_film_lead_90s",
    }


# Example model outputs: which lines may be shown. Jokes target the photo, never the person.
ROAST_EXAMPLES = [
    ("That ceiling light is auditioning for interrogation-room drama.", True),
    ("The background plant is the real main character here.", True),
    ("Many thanks to the spotlight for the free mugshot vibes.", True),
    ("This blur says 'taken mid-sneeze by a friend on a moving bus'.", True),
    ("Bold of you to pose in front of a laundry pile.", True),
    ("那盆绿植比你还抢镜。", True),
    ("这张照片的光线像在审讯室里拍的。", True),
    ("Your nose is doing a lot of work here.", False),
    ("Acne cameo in the corner.", False),
    ("Looks like a young Tony Leung.", False),
    ("Total celebrity look-alike energy.", False),
    ("Gaining a little weight suits you.", False),
    ("Very teen-drama energy for someone your age.", False),
    ("Is that a receding hairline or the lighting?", False),
    ("你长得像某个明星。", False),
    ("下巴的角度有点奇怪。", False),
    ("看起来比实际年龄老。", False),
]


@pytest.mark.parametrize(("line", "shown"), ROAST_EXAMPLES)
def test_roast_examples_target_the_photo_never_the_person(line, shown):
    assert roast_lines([line]) == ([line] if shown else [])


APPEARANCE_EXAMPLES = [
    ("Warm, open smile that reaches your eyes.", True),
    ("Bold brows frame your eyes well.", True),
    ("Deep greens and navy flatter you.", True),
    ("Your skin looks radiant in soft window light.", True),
    ("笑容很有感染力。", True),
    ("侧光让轮廓更立体。", True),
    ("One small flaw: your nose.", False),
    ("Fillers could balance your lips.", False),
    ("A low-carb diet would sharpen your face.", False),
    ("You look younger with short hair.", False),
    ("Your ethnic features stand out.", False),
    ("建议考虑医美调整。", False),
    ("减肥后会更上镜。", False),
]


@pytest.mark.parametrize(("line", "shown"), APPEARANCE_EXAMPLES)
def test_appearance_examples_are_constructive_only(line, shown):
    assert appearance_lines([line]) == ([line] if shown else [])


def test_no_joke_rather_than_a_joke_that_breaks_the_rules():
    photos = parse_response(
        gemini_reply(
            [photo_json(0, roast=["Your teeth glow", "Acne says hi"], vibe="indie_band_frontman")]
        ),
        1,
    ).photos
    joke = ranked_photos(photos, "gentle")[0].roast
    assert joke is not None and joke.lines == [] and joke.vibe == "indie_band_frontman"


def test_vibe_can_only_be_an_archetype_never_a_person():
    with pytest.raises(ProviderError, match="invalid_response"):
        parse_response(gemini_reply([photo_json(0, vibe="Tony Leung")]), 1)


def test_never_sends_or_stores_more_than_five_or_undecodable_photos(credits):
    register(credits.client)
    transport = FakeTransport([])
    configure(credits, transport)
    accept(credits)
    assert submit(credits, 6).status_code == 422
    response = credits.client.post(
        BASE + "/analyses",
        json={
            "photos": [base64.b64encode(b"not an image").decode()],
            "self_and_adult_confirmed": True,
        },
        headers=csrf_headers(credits.client),
    )
    assert response.status_code == 422 and response.json()["detail"] == "photo_check_invalid_photos"
    assert transport.calls == []


def test_global_budget_pauses_the_check_before_it_can_be_exceeded(credits):
    register(credits.client)
    transport = FakeTransport([ok()])
    # A full five-photo reservation is 1400+3500 input and 2550 output tokens: 7845 micro-USD.
    configure(credits, transport, free_hook_daily_budget_usd=Decimal("0.009"))
    accept(credits)
    assert submit(credits).status_code == 200
    current = status(credits)
    assert current["available"] is False and current["reason"] == "paused"
    paused = submit(credits)
    assert paused.status_code == 503 and paused.json()["detail"] == "photo_check_paused"
    assert len(transport.calls) == 1
    with credits.sessions() as session:
        budget = session.scalars(select(PhotoCheckBudgetDay)).one()
    assert budget.paused_at is not None and budget.reserved_micro_usd == 0


def test_abandoned_reservations_are_charged_conservatively_and_credits_refunded(credits):
    user = register(credits.client)
    public = user["public_user_id"]
    configure(credits, FakeTransport([ok()]))
    accept(credits)
    grant(credits, public, 1)
    service = PhotoCheckService(credits.sessions, credits.client.app.state.settings)
    day = service.today()
    owner_id = account(credits, public).id
    with credits.sessions.begin() as session:
        session.add(PhotoCheckBudgetDay(day=day, spent_micro_usd=0, reserved_micro_usd=999))
        stale = PhotoCheckAnalysis(
            user_id=owner_id,
            day=day,
            status="RESERVED",
            photo_count=1,
            language="en",
            model="m",
            prompt_version="p",
            consent_version=CONSENT_VERSION,
            reserved_micro_usd=999,
            funding="credits",
            credits_charged=1,
            created_at=now() - timedelta(hours=1),
        )
        session.add(stale)
        session.flush()
        append_credit(
            session,
            lock_wallet(session, owner_id),
            amount=-1,
            kind="PHOTO_CHECK",
            reference_type="photo_check",
            reference_id=str(stale.id),
            key=f"photo-check:{stale.id}",
        )
    assert balance(credits, public) == 0
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
    assert balance(credits, public) == 1  # No result was delivered: refunded.


def test_blocked_and_invalid_responses_never_become_results():
    usage_reply = gemini_reply([photo_json(0)], finish="SAFETY")
    with pytest.raises(ProviderError) as blocked:
        parse_response(usage_reply, 1)
    assert blocked.value.reason == "blocked" and blocked.value.usage is not None
    with pytest.raises(ProviderError, match="invalid_response"):
        parse_response(gemini_reply([photo_json(1)]), 1)  # Wrong index.
    for broken in (
        {**photo_json(0), "sharpness": None},
        {**photo_json(0), "lighting": 11},
        {**photo_json(0), "band": None},
        {**photo_json(0), "band": 5},
    ):
        with pytest.raises(ProviderError, match="invalid_response"):
            parse_response(gemini_reply([broken]), 1)
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


def test_weeks_start_on_monday_utc():
    assert week_start(date(2026, 11, 25)) == date(2026, 11, 23)  # Wednesday -> Monday.
    assert week_start(date(2026, 11, 23)) == date(2026, 11, 23)
    assert week_start(date(2026, 11, 29)) == date(2026, 11, 23)  # Sunday stays in the week.


def test_consistency_report_counts_gate_and_band_agreement():
    runs = [
        {"band": 3, **{name: 7 for name in CRITERIA}},
        {"band": 3, **{name: 8 for name in CRITERIA}},
        {"band": 2, **{name: 7 for name in CRITERIA}},
        {"band": 4, **dict(zip(CRITERIA, (5, 6, 6, 6, 6, 6), strict=True))},  # 5.8: below.
        {"refusal": "multiple_people"},
    ]
    report = summarize(runs)
    assert report[0].startswith("run 1: quality 7.0 gate=passed band=3 ")
    assert report[3].startswith("run 4: quality 5.8 gate=failed band=- ")
    assert report[4] == "run 5: no result (multiple_people), gate=failed"
    assert "quality gate agreement: 3/5 runs passed (60%; gate is 6.0/10)" in report
    # Only runs that passed count towards band agreement: the failed run's band 4 is ignored.
    assert "band agreement (runs that passed the gate): 2/3 gave band 3 (67%)" in report
    assert "lighting: min 5, max 8, spread 3" in report


def test_consistency_report_when_no_run_passes_the_gate():
    report = summarize([{"band": 3, **{name: 5 for name in CRITERIA}}] * 2)
    assert "quality gate agreement: 2/2 runs failed (100%; gate is 6.0/10)" in report
    assert "band agreement: no run passed the quality gate, so no band is shown" in report


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


# --- Two stages: appearance only for photos that pass the quality gate ------------------------


@pytest.mark.parametrize(
    ("raw_score", "passed"), [(5.9, False), (5.99, False), (6.0, True), (8.5, True), (None, False)]
)
def test_quality_gate_threshold(raw_score, passed):
    assert QUALITY_GATE == 6.0
    assert passes_quality_gate(raw_score) is passed


def test_photos_below_the_gate_keep_technique_feedback_but_lose_stage_two():
    photos = parse_response(
        gemini_reply(
            [
                photo_json(0, scores=(6, 6, 6, 6, 6, 5), band=4, roast=["Nice light"]),  # 5.83
                photo_json(1, scores=(6, 6, 6, 6, 6, 6), band=2, roast=["Nice light"]),  # 6.0
                photo_json(2, "no_person"),
            ]
        ),
        3,
    ).photos
    below, exactly, nobody = ranked_photos(photos, "gentle")
    assert below.usable and below.quality_passed is False
    assert below.raw_score == pytest.approx(35 / 6) and below.scores is not None
    assert below.tips == ["Face the window"]  # Stage 1 feedback is always shown.
    assert below.appearance is None and below.roast is None  # No band, no roast.
    assert exactly.quality_passed is True and exactly.raw_score == 6.0
    assert exactly.appearance is not None and exactly.appearance.band == 2
    assert exactly.roast is not None and exactly.roast.lines == ["Nice light"]
    assert nobody.quality_passed is False and nobody.appearance is None
    # Ranking stays by technique score, gate or not.
    assert (exactly.rank, below.rank, nobody.rank) == (1, 2, None)


def test_contract_requires_quality_passed():
    fields = PhotoCheckPhoto.model_fields
    assert fields["quality_passed"].is_required() and fields["quality_passed"].annotation is bool


def test_api_never_returns_or_stores_stage_two_for_a_photo_below_the_gate(credits):
    register(credits.client)
    low = photo_json(0, scores=(5, 6, 6, 6, 6, 6), band=4, roast=["Moody lighting"])
    transport = FakeTransport([ok(), (200, gemini_reply([low, photo_json(1)]))])
    configure(credits, transport)
    accept(credits)
    assert submit(credits).status_code == 200  # Unlocks roast for the next check.
    result = submit(credits, 2, roast="spicy").json()
    by_index = {photo["index"]: photo for photo in result["photos"]}
    assert by_index[0]["quality_passed"] is False
    assert by_index[0]["appearance"] is None and by_index[0]["roast"] is None
    assert by_index[0]["display_score"] == 5.8 and by_index[0]["rank"] == 2
    assert by_index[1]["quality_passed"] is True and by_index[1]["appearance"]["band"] == 3
    with credits.sessions() as session:
        stored = session.scalars(
            select(PhotoCheckAnalysis).order_by(PhotoCheckAnalysis.created_at.desc())
        ).first()
    low_stored = next(photo for photo in stored.result["photos"] if photo["index"] == 0)
    assert low_stored["appearance"] is None and low_stored["roast"] is None
    assert "band" not in json.dumps(low_stored)
