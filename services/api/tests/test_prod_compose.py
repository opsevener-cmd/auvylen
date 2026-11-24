"""Static checks of docker-compose.prod.yml against the application's own settings."""

import re
from pathlib import Path

from aevyra_api.config import Settings

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = (ROOT / "docker-compose.prod.yml").read_text()


def test_compose_limit_defaults_match_application_defaults():
    block = COMPOSE.split("x-app-environment: &app-environment", 1)[1].split("\nservices:", 1)[0]
    defaults = dict(re.findall(r"\$\{([A-Z_]+):-(\d+)\}", block))
    names = [
        n
        for n in defaults
        if n.startswith(("RESEARCH_MAX", "RESEARCH_DAILY", "OWNER_", "JOB_", "STUDY_"))
    ]
    assert len(names) >= 14
    fields = Settings.model_fields
    for name in names:
        assert int(defaults[name]) == fields[name.lower()].default, name


def test_private_volume_reaches_only_api_and_worker():
    services = COMPOSE.split("\nservices:\n", 1)[1].split("\nnetworks:\n", 1)[0]
    blocks = re.split(r"\n  (?=[a-z]+:\n)", "\n" + services)
    mounts = {
        b.split(":", 1)[0].strip(): "auvylen_private:/var/lib/auvylen" in b
        for b in blocks
        if b.strip()
    }
    assert mounts == {
        "web": False,
        "api": True,
        "worker": True,
        "postgres": False,
        "redis": False,
        "proxy": False,
    }
    assert "profiles: [research]" in COMPOSE


def test_free_hook_compose_defaults_match_application_defaults():
    from decimal import Decimal

    block = COMPOSE.split("x-app-environment: &app-environment", 1)[1].split("\nservices:", 1)[0]
    defaults = dict(re.findall(r"(FREE_HOOK_[A-Z_]+): \$\{\1:-([^}]*)\}", block))
    fields = Settings.model_fields
    assert set(defaults) == {
        "FREE_HOOK_ENABLED",
        "FREE_HOOK_PAID_TIER_CONFIRMED",
        "FREE_HOOK_MODEL",
        "FREE_HOOK_USER_DAILY_LIMIT",
        "FREE_HOOK_DAILY_BUDGET_USD",
        "FREE_HOOK_PRICE_INPUT_PER_M",
        "FREE_HOOK_PRICE_OUTPUT_PER_M",
        "FREE_HOOK_THINKING_LEVEL",
    }
    for name, value in defaults.items():
        default = fields[name.lower()].default
        parsed = {bool: lambda v: v == "true", int: int, Decimal: Decimal, str: str}[type(default)]
        assert parsed(value) == default, name
    # Never enabled, keyed or paid-tier-confirmed by default.
    assert "GEMINI_API_KEY: ${GEMINI_API_KEY:-}" in block
    assert defaults["FREE_HOOK_ENABLED"] == defaults["FREE_HOOK_PAID_TIER_CONFIRMED"] == "false"


def test_caddy_allows_photo_check_uploads():
    routes = (ROOT / "infra/caddy/routes.caddy").read_text()
    upload = routes.split("@preference_upload path", 1)[1].split("\n", 1)[0]
    other = routes.split("@other_requests not path", 1)[1].split("\n", 1)[0]
    assert "/api/v1/photo-check/analyses" in upload and "/api/v1/photo-check/analyses" in other
