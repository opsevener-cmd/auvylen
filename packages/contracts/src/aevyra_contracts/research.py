from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["mock", "custom", "comboloss", "fpem", "faclip", "swingfvqa-ca"] = "mock"
    idempotency_key: UUID


class ResearchJobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    provider: str
    kind: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    result: dict[str, JsonValue] | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class ProviderView(BaseModel):
    slug: str
    display_name: str
    available: bool
    reason: str


class ResearchStatus(BaseModel):
    enabled: bool
    authorized: bool
    synthetic_available: bool
    providers: list[ProviderView]
