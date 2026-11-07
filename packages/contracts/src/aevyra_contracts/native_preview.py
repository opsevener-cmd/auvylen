"""Laboratory preview wire format; deliberately not an EngineScore or a 1–10 result."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NativePreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predicted_rating: float = Field(ge=1, le=7, allow_inf_nan=False)
    native_scale: tuple[Literal[1], Literal[7]]
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    encoder: str
    collection: str
    research_only: Literal[True]
    synthetic: Literal[False]
    consumer_enabled: Literal[False]
    release_failures: list[str]
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    peak_rss_kib: int = Field(ge=0)
