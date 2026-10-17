"""Strict administrative commands; all responses intentionally exclude private artifacts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class AdminCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("A meaningful non-sensitive audit reason is required")
        return value.strip()


class UserStatusCommand(AdminCommand):
    disabled: bool = Field(strict=True)


class ResearchAccessCommand(AdminCommand):
    enabled: bool = Field(strict=True)


class CreditGrantCommand(AdminCommand):
    amount: int = Field(ge=1, le=1000000, strict=True)


class BatchCreateCommand(AdminCommand):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    channel: str = Field(default="owner", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    sku: str = Field(default="promotion", pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    credits: int = Field(ge=1, le=1000000, strict=True)
    quantity: int = Field(ge=1, le=100, strict=True)
    expires_days: int = Field(default=30, ge=1, le=365)


class AdminResult(BaseModel):
    data: dict[str, JsonValue]


class AdminPage(BaseModel):
    items: list[dict[str, JsonValue]]
    total: int
    page: int
    page_size: int


class OwnerOverview(BaseModel):
    counts: dict[str, int]
    jobs: dict[str, int]
    credits: dict[str, int]
    health: dict[str, JsonValue]
    providers: list[dict[str, JsonValue]]
    extractors: list[dict[str, JsonValue]]
    usage: list[dict[str, JsonValue]]
    quotas: dict[str, int]
    environment: str
    research_enabled: bool
    free_product_access: Literal[True] = True
