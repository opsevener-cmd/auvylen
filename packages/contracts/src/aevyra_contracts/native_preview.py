"""Laboratory preview wire format; deliberately not an EngineScore or a 1–10 result."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InputCheck(BaseModel):
    """How far the image's features lie from the training portraits (coarse guard)."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["typical", "unusual", "outside", "unchecked"]
    distance: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    caution_above: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    outside_above: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class NativePreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # None only when the input check says the image is outside the training portraits.
    predicted_rating: float | None = Field(ge=1, le=7, allow_inf_nan=False)
    input_check: InputCheck = InputCheck(verdict="unchecked")
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

    @model_validator(mode="after")
    def score_only_for_comparable_inputs(self) -> "NativePreviewResult":
        if (self.predicted_rating is None) != (self.input_check.verdict == "outside"):
            raise ValueError("A score is withheld exactly when the input is outside")
        return self
