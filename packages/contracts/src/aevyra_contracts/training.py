from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: UUID
    extractor: Literal["rgb-grid-texture-v1", "mobilenetv3-small-imagenet-onnx-v1"] = (
        "rgb-grid-texture-v1"
    )
    idempotency_key: UUID
    alpha: float = Field(default=10.0, gt=0, le=1000, allow_inf_nan=False)
    seed: int = Field(default=42, ge=0, le=2147483647)
    validation_fraction: float = Field(default=0.2, ge=0.1, le=0.4, allow_inf_nan=False)


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: UUID
    dataset_id: UUID
    image_id: UUID
    idempotency_key: UUID


class ModelEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    archived: bool


class ModelView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset_id: UUID | None
    project_id: UUID
    version: int
    state: Literal["TRAINING", "READY", "FAILED", "ARCHIVED", "DELETED"]
    training_job_id: UUID
    extractor: str
    implementation: str
    configuration: dict[str, JsonValue]
    metrics: dict[str, JsonValue] | None
    limitations: list[str]
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime


class ExtractorView(BaseModel):
    id: str
    available: bool
    reason: str
    manifest: dict[str, JsonValue]
