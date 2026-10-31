from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectCreate(Input):
    name: str = Field(min_length=1, max_length=120)


class ProjectView(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class DatasetCreate(ProjectCreate):
    project_id: UUID
    source: str = Field(min_length=1, max_length=500)
    source_url: str = Field(default="", max_length=500)
    license: str = Field(min_length=1, max_length=500)
    adult_authorized_consent: Literal[True]
    retention_days: int = Field(default=30, ge=1, le=90)
    rating_min: int = Field(default=1, ge=0, le=99)
    rating_max: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def valid_scale(self) -> "DatasetCreate":
        if self.rating_min >= self.rating_max:
            raise ValueError("Invalid rating scale")
        return self


class DatasetEdit(ProjectCreate):
    archived: bool


class DatasetView(ProjectView):
    project_id: UUID
    source: str
    source_url: str
    license: str
    rating_min: int
    rating_max: int
    archived: bool
    expires_at: datetime
    image_count: int
    rated_count: int
    compared_count: int
    # Included in image_count (and storage quota); never rated, compared or trained on.
    prediction_count: int = 0


class ImageUploadMetadata(Input):
    adult_authorized_consent: Literal[True]
    subject_group: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: Literal["annotation", "prediction"] = "annotation"


class ImageUpload(ImageUploadMetadata):
    content_base64: str = Field(min_length=1, max_length=5592408)


class ImageEdit(Input):
    subject_group: str | None = Field(default=None, min_length=1, max_length=120)
    excluded: bool


class RatingInput(Input):
    score: float | None = Field(allow_inf_nan=False)


class ImageView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset_id: UUID
    width: int
    height: int
    subject_group: str | None
    excluded: bool
    created_at: datetime
    score: float | None
    rating_recorded: bool
    purpose: Literal["annotation", "prediction"] = "annotation"


class PairInput(Input):
    left_id: UUID
    right_id: UUID
    choice: Literal["left", "right", "equal", "skip"]


class PairView(PairInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    updated_at: datetime


class DatasetDetail(BaseModel):
    dataset: DatasetView
    images: list[ImageView]
    pairs: list[PairView]


ReadinessReason = Literal[
    "archived",
    "too_few_ratings",
    "too_few_groups",
    "insufficient_split",
    "no_score_variation",
    "too_many_ratings",
]


class TrainingReadiness(BaseModel):
    """Same checks as training submission, so the interface never offers an invalid request."""

    eligible: bool
    reasons: list[ReadinessReason]
    rated: int
    required_ratings: int
    groups: int
    required_groups: int
    awaiting: int
    skipped: int
    excluded: int
    prediction_only: int
