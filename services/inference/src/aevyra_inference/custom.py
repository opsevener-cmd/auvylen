"""Permanent custom-model contracts, independent of third-party plugins.

No training algorithm or image-import HTTP endpoint is implemented here.
"""

from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatasetSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    dataset_id: UUID
    owner_id: UUID
    version: int = Field(ge=1)
    image_artifact_ids: list[UUID] = Field(min_length=1, max_length=10000)
    consent_reference: str = Field(min_length=1, max_length=200)


class Rating(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    image_artifact_id: UUID
    rating: float = Field(ge=0, le=10, allow_inf_nan=False)
    annotator_id: UUID


class PairwisePreference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    left_artifact_id: UUID
    right_artifact_id: UUID
    preferred_artifact_id: UUID | None  # None explicitly represents a tie.
    annotator_id: UUID

    @model_validator(mode="after")
    def distinct_pair(self) -> "PairwisePreference":
        if self.left_artifact_id == self.right_artifact_id or self.preferred_artifact_id not in {
            None,
            self.left_artifact_id,
            self.right_artifact_id,
        }:
            raise ValueError("Invalid preference pair")
        return self


class CheckpointManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_id: UUID
    owner_id: UUID
    version: int = Field(ge=1)
    dataset_id: UUID
    dataset_version: int = Field(ge=1)
    checkpoint_artifact_id: UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_implementation: str = Field(min_length=1, max_length=200)
    provenance_reference: str = Field(min_length=1, max_length=200)


class CustomTrainer(Protocol):
    def train(
        self,
        dataset: DatasetSnapshot,
        ratings: list[Rating],
        preferences: list[PairwisePreference],
        output_root: Path,
    ) -> CheckpointManifest: ...


class DatasetRepository(Protocol):
    """Future persistence must validate ownership/consent on every mutation."""

    def create(self, owner_id: UUID, consent_reference: str) -> UUID: ...

    def add_image(self, owner_id: UUID, dataset_id: UUID, artifact_id: UUID) -> None: ...

    def record_rating(self, owner_id: UUID, dataset_id: UUID, rating: Rating) -> None: ...

    def record_preference(
        self, owner_id: UUID, dataset_id: UUID, preference: PairwisePreference
    ) -> None: ...

    def snapshot(self, owner_id: UUID, dataset_id: UUID) -> DatasetSnapshot: ...
