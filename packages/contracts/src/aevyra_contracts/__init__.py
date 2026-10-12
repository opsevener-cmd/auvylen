from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EngineMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    display_name: str
    version: str
    licensing_status: str
    provenance: str
    commercial_allowed: bool
    research_allowed: bool = False
    production_enabled: bool
    synthetic: bool


class ScoringResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    raw_score: float
    display_score: float
    engine: str
    version: str
    calibration_version: str | None = None
    timestamp: str
    synthetic: bool


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["aevyra-api"] = "aevyra-api"


class Dependencies(BaseModel):
    database: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: Dependencies


class EngineListResponse(BaseModel):
    engines: list[EngineMetadata] = Field(default_factory=list)
