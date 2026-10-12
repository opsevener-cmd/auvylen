import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from aevyra_api import migrate
from aevyra_api.config import Settings


def test_migrations_require_explicit_operator_authorization(monkeypatch):
    monkeypatch.delenv("APPLY_MIGRATIONS", raising=False)
    with pytest.raises(SystemExit, match="backup/review"):
        migrate.main()


def test_mock_checkout_can_be_disabled_in_private_staging(commerce):
    commerce.client.app.state.settings.mock_checkout_enabled = False
    response = commerce.client.post("/api/v1/orders", json={"product_slug": "aevyra-test-analysis"})
    assert response.status_code == 404


def test_unknown_provider_configuration_rejected():
    with pytest.raises(ValueError, match="Unknown enabled"):
        Settings(
            api_environment="test", enabled_model_providers=["random-fallback"], _env_file=None
        )


@pytest.mark.integration
def test_cloud_compose_ports_volumes_and_startup_gate():
    docker = shutil.which("docker")
    if docker is None and os.environ.get("LOCALAPPDATA"):
        candidate = (
            Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe"
        )
        if candidate.exists():
            docker = str(candidate)
    assert docker is not None, "Docker Compose is required for this integration check"
    root = Path(__file__).resolve().parents[3]
    environment = {
        **os.environ,
        "DATABASE_URL": "postgresql+psycopg://test:testing-only-long-password@postgres/aevyra",
        "REDIS_URL": "redis://redis:6379/0",
        "POSTGRES_PASSWORD": "testing-only-long-password",
        "REDEMPTION_CODE_PEPPER": "test-only-pepper-not-for-deployment-12345",
        "CORS_ORIGINS": "[]",
        "AEVYRA_DOMAIN": "example.test",
        "APP_ENV": "production",
    }
    result = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            ".env.cloud.example",
            "-f",
            "docker-compose.prod.yml",
            "-f",
            "docker-compose.cloud.yml",
            "--profile",
            "research",
            "config",
            "--format",
            "json",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, "Cloud Compose validation failed"
    config = json.loads(result.stdout)
    services = config["services"]
    assert all(not service.get("ports") for name, service in services.items() if name != "proxy")
    assert sorted(port["published"] for port in services["proxy"]["ports"]) == ["443", "80"]
    assert config["networks"]["data"]["internal"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert (
        services["worker"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    )
    assert services["migrate"]["restart"] == "no"
    assert services["api"]["environment"]["MOCK_CHECKOUT_ENABLED"] == "false"
    assert {"private_models", "private_uploads", "postgres_data", "redis_data"} <= set(
        config["volumes"]
    )
    assert not services["web"].get("volumes")
    assert not any("private_" in mount["source"] for mount in services["proxy"]["volumes"])
