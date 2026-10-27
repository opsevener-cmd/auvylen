from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class AestheticUploadMetadata(BaseModel):
    """Attestations are recorded, not inferred: no age is estimated from a face."""

    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    adult_subject_attested: Literal[True]
    single_subject_attested: Literal[True]
    authorized_consent: Literal[True]


class AestheticModelCard(BaseModel):
    model_version: str
    calibration_version: str
    implementation: str
    extractor: str
    dataset_name: str
    dataset_license: str
    annotator_population: str
    synthetic: bool
    test_images: int
    test_subjects: int
    test_mae: float
    mean_baseline_mae: float
    test_spearman: float | None
    test_distribution_loss: float
    mean_distribution_baseline_loss: float
    interval_level: float
    interval_half_width: float | None
    interval_test_coverage: float | None


class AestheticStatus(BaseModel):
    enabled: bool
    authorized: bool
    available: bool
    reason: str
    model: AestheticModelCard | None
    limitations: list[str]


class AestheticResult(BaseModel):
    raw_score: float
    display_score: float
    engine: str
    version: str
    calibration_version: str
    timestamp: str
    synthetic: bool
    score_10: Annotated[float, Field(ge=1, le=10)]
    expected_rating_5: Annotated[float, Field(ge=1, le=5)]
    rating_distribution: Annotated[list[Probability], Field(min_length=5, max_length=5)]
    rating_spread_10: float
    interval_level: float
    interval_low: float | None
    interval_high: float | None
    extractor: str
    processing_duration_ms: float
    adult_basis: Literal["user_attestation"]
    single_subject_basis: Literal["user_attestation"]
    automated_face_detection: Literal["not_implemented"]


class AestheticAnalysisView(BaseModel):
    id: UUID
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    progress: int
    phase: str
    failure_reason: str | None
    model_version: str
    image_retained: bool
    result: AestheticResult | None
    created_at: datetime
    completed_at: datetime | None
