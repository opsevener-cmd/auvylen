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
    # None for an outside input or an unavailable input check. Legacy scored records stay readable.
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
        if self.input_check.verdict == "outside" and self.predicted_rating is not None:
            raise ValueError("Outside inputs must not have a score")
        if self.predicted_rating is None and self.input_check.verdict not in {
            "outside",
            "unchecked",
        }:
            raise ValueError("Comparable checked inputs require a score")
        if self.input_check.verdict != "unchecked":
            check = self.input_check
            if (
                check.distance is None
                or check.caution_above is None
                or check.outside_above is None
                or check.caution_above >= check.outside_above
            ):
                raise ValueError("Checked results require ordered thresholds and a finite distance")
            expected = (
                "outside"
                if check.distance > check.outside_above
                else "unusual"
                if check.distance > check.caution_above
                else "typical"
            )
            if check.verdict != expected:
                raise ValueError("Input verdict disagrees with its distance")
        return self
