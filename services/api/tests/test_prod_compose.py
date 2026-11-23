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
