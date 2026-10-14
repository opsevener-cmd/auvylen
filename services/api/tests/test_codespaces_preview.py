"""Codespaces origin/credential safeguards; real service lifecycle is browser-tested."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "codespaces_preview", Path(__file__).resolve().parents[3] / "scripts/codespaces-preview.py"
)
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


def test_codespaces_origin_is_exact_and_local_execution_is_rejected(monkeypatch):
    monkeypatch.delenv("AUVYLEN_PREVIEW_TEST", raising=False)
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(SystemExit, match="only inside"):
        preview.context()
    monkeypatch.setenv("CODESPACES", "true")
    monkeypatch.setenv("CODESPACE_NAME", "quiet-cloud-ab123")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    assert preview.context()[1] == "https://quiet-cloud-ab123-3000.app.github.dev"
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "attacker.example")
    with pytest.raises(SystemExit, match="Unexpected"):
        preview.context()
    monkeypatch.setenv("AUVYLEN_PREVIEW_TEST", "1")
    monkeypatch.setenv("AUVYLEN_PREVIEW_TEST_ORIGIN", "https://attacker.example")
    with pytest.raises(SystemExit, match="loopback"):
        preview.context()


def test_preview_keeps_credentials_and_security_defaults(tmp_path, monkeypatch):
    secret = tmp_path / "secrets"
    secret.mkdir()
    # Local synthetic test credential; never an actual preview secret.
    (secret / "postgres-password").write_text("a" * 96)
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, b"f")
    )
    data = tmp_path / "data"
    origin = "https://quiet-cloud-ab123-3000.app.github.dev"
    first = preview.environment(data, origin, secret)
    second = preview.environment(data, origin, secret)
    assert first["REDEMPTION_CODE_PEPPER"] == second["REDEMPTION_CODE_PEPPER"]
    assert len(first["REDEMPTION_CODE_PEPPER"]) == 96
    assert (data / "credentials.json").stat().st_mode & 0o777 == 0o600
    assert first["SESSION_COOKIE_SECURE"] == "true"
    assert json.loads(first["CORS_ORIGINS"]) == [origin]
    assert first["RESEARCH_MODE"] == "true"
    assert first["MOCK_CHECKOUT_ENABLED"] == "false"
    assert first["PUBLIC_PILOT"] == "false"
    assert first["API_URL"] == "http://127.0.0.1:8000"
    (secret / "postgres-password").write_text("b" * 96)
    with pytest.raises(SystemExit, match="do not match"):
        preview.environment(data, origin, secret)


def test_missing_app_credentials_never_replace_existing_database_pepper(tmp_path, monkeypatch):
    secret = tmp_path / "secrets"
    secret.mkdir()
    (secret / "postgres-password").write_text("a" * 96)
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, b"t")
    )
    data = tmp_path / "data"
    with pytest.raises(SystemExit, match="lost app credentials"):
        preview.environment(data, "https://example.app.github.dev", secret)
    assert not (data / "credentials.json").exists()
