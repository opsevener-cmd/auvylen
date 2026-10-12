import ipaddress
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    api_environment: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "API_ENVIRONMENT", "api_environment"),
    )
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://aevyra:aevyra_dev_only@127.0.0.1:5432/aevyra"
    )
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    payment_provider: Literal["mock"] = "mock"
    mock_checkout_enabled: bool = True
    redemption_code_pepper: SecretStr | None = None
    session_lifetime_seconds: int = Field(default=86400, ge=300, le=604800)
    session_cookie_secure: bool = False
    public_pilot: bool = False
    public_base_url: str | None = None
    research_mode: bool = False
    shared_proxy_rate_limits: bool = False
    enabled_model_providers: list[str] = []
    private_upload_root: Path = Path("/var/lib/auvylen/uploads")
    private_model_root: Path = Path("/var/lib/auvylen/models")
    research_max_pending: int = Field(default=2, ge=1, le=10)
    research_daily_limit: int = Field(default=50, ge=1, le=1000)
    worker_queue: Literal["cpu", "gpu"] = "cpu"
    job_lease_seconds: int = Field(default=60, ge=30, le=3600)

    @model_validator(mode="after")
    def production_defaults(self) -> "Settings":
        if any(
            slug not in {"custom", "comboloss", "fpem", "faclip", "swingfvqa-ca"}
            for slug in self.enabled_model_providers
        ):
            raise ValueError("Unknown enabled model provider")
        if self.public_pilot:
            if self.api_environment != "staging":
                raise ValueError("PUBLIC_PILOT requires APP_ENV=staging")
            try:
                origin = urlsplit(self.public_base_url or "")
                hostname = origin.hostname or ""
                port = origin.port
            except ValueError:
                raise ValueError("PUBLIC_BASE_URL must be a canonical HTTPS origin") from None
            if (
                origin.scheme != "https"
                or origin.username is not None
                or origin.password is not None
                or origin.path
                or origin.query
                or origin.fragment
                or hostname == "localhost"
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", hostname)
                or "." not in hostname
                or ".." in hostname
                or self.public_base_url != f"https://{hostname}" + (f":{port}" if port else "")
            ):
                raise ValueError("PUBLIC_BASE_URL must be a canonical HTTPS origin")
            try:
                ipaddress.ip_address(hostname)
            except ValueError:
                pass
            else:
                raise ValueError("PUBLIC_BASE_URL requires a public DNS hostname")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS is forbidden")
            self.cors_origins = [self.public_base_url]
        elif self.public_base_url is not None:
            raise ValueError("PUBLIC_BASE_URL requires explicit PUBLIC_PILOT mode")
        if self.api_environment != "test" and (
            self.redemption_code_pepper is None
            or len(self.redemption_code_pepper.get_secret_value()) < 32
            or self.redemption_code_pepper.get_secret_value().startswith("REPLACE_")
        ):
            raise ValueError("REDEMPTION_CODE_PEPPER requires a securely generated secret")
        if self.api_environment in {"staging", "production"}:
            self.session_cookie_secure = True
        if self.api_environment in {"staging", "production"}:
            try:
                url = make_url(self.database_url.get_secret_value())
            except Exception:
                raise ValueError("Invalid database configuration") from None
            if (
                "database_url" not in self.model_fields_set
                or url.drivername != "postgresql+psycopg"
                or not url.host
                or not url.database
                or not url.username
                or not url.password
                or len(url.password) < 24
                or "aevyra_dev_only" in url.password
                or url.password.startswith("REPLACE_")
            ):
                raise ValueError(
                    "Deployment requires explicit database credentials of at least 24 characters"
                )
            if (
                "redis_url" not in self.model_fields_set
                or not self.redis_url.get_secret_value().startswith(("redis://", "rediss://"))
            ):
                raise ValueError("Deployment requires an explicit Redis URL")
            if "cors_origins" not in self.model_fields_set or "*" in self.cors_origins:
                raise ValueError("Deployment CORS must be explicitly configured")
            if self.api_environment == "production" and any(
                not origin.startswith("https://") for origin in self.cors_origins
            ):
                raise ValueError("Production CORS origins must use HTTPS")
            if self.log_level == "DEBUG":
                raise ValueError("Deployment debug logging is disabled")
        return self
