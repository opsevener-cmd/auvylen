"""Versioned CPU rating regression over handcrafted or frozen pretrained visual features."""

import hashlib
import math
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from aevyra_contracts import EngineMetadata
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from aevyra_inference.engine import ScoringEngine
from aevyra_inference.extractors import MOBILENET, create_extractor, dimension, manifest

EXTRACTOR = "rgb-grid-texture-v1"
IMPLEMENTATION = "rating-ridge-v1"
DIMENSION = 230
MIN_RATED_IMAGES = 8
MIN_GROUPS = 5
Finite = Annotated[float, Field(allow_inf_nan=False)]
Vector = Annotated[list[Finite], Field(min_length=DIMENSION, max_length=DIMENSION)]


class RidgeCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["auvylen-rating-ridge-v1"] = "auvylen-rating-ridge-v1"
    extractor: Literal["rgb-grid-texture-v1"] = "rgb-grid-texture-v1"
    implementation: Literal["rating-ridge-v1"] = "rating-ridge-v1"
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mean: Vector
    scale: Annotated[
        list[Annotated[float, Field(gt=0, allow_inf_nan=False)]],
        Field(min_length=DIMENSION, max_length=DIMENSION),
    ]
    coefficients: Vector
    intercept: Finite
    rating_min: Finite
    rating_max: Finite


class PretrainedRidgeCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["auvylen-rating-ridge-v2"] = "auvylen-rating-ridge-v2"
    extractor: Literal["mobilenetv3-small-imagenet-onnx-v1"] = "mobilenetv3-small-imagenet-onnx-v1"
    implementation: Literal["rating-ridge-v1"] = "rating-ridge-v1"
    representation: dict[str, JsonValue]
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mean: Annotated[list[Finite], Field(min_length=1024, max_length=1024)]
    scale: Annotated[
        list[Annotated[float, Field(gt=0, allow_inf_nan=False)]],
        Field(min_length=1024, max_length=1024),
    ]
    coefficients: Annotated[list[Finite], Field(min_length=1024, max_length=1024)]
    intercept: Finite
    rating_min: Finite
    rating_max: Finite

    @model_validator(mode="after")
    def verify_representation(self) -> "PretrainedRidgeCheckpoint":
        if self.representation != manifest(self.extractor) or self.rating_min >= self.rating_max:
            raise ValueError("Checkpoint representation or rating bounds mismatch")
        return self


RatingCheckpoint = RidgeCheckpoint | PretrainedRidgeCheckpoint
checkpoint_adapter: TypeAdapter[RatingCheckpoint] = TypeAdapter(RatingCheckpoint)


def extract(payload: bytes) -> list[float]:
    """Spatial RGB, coarse gradients and color moments. No face or identity recognition."""
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError("Image size limit")
    with Image.open(BytesIO(payload), formats=["JPEG", "PNG"]) as image:
        if image.width > 4096 or image.height > 4096 or image.width * image.height > 16_000_000:
            raise ValueError("Image dimensions limit")
        rgb = image.convert("RGB")
        grid = np.asarray(rgb.resize((8, 8), Image.Resampling.BOX), dtype=np.float64) / 255.0
        gray = np.asarray(rgb.convert("L").resize((32, 32)), dtype=np.float64) / 255.0
    gradients = np.stack([np.gradient(gray, axis=0), np.gradient(gray, axis=1)], axis=-1)
    texture = np.abs(gradients).reshape(4, 8, 4, 8, 2).mean(axis=(1, 3)).ravel()
    features = np.concatenate(
        (grid.ravel(), texture, grid.mean(axis=(0, 1)), grid.std(axis=(0, 1)))
    )
    if features.shape != (DIMENSION,) or not np.isfinite(features).all():
        raise ValueError("Invalid visual features")
    return [float(value) for value in features]


def split_groups(groups: list[str], seed: int, fraction: float) -> tuple[list[int], list[int]]:
    unique = sorted(
        set(groups), key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).digest()
    )
    if len(groups) < MIN_RATED_IMAGES or len(unique) < MIN_GROUPS:
        raise ValueError(
            "At least 8 rated images and 5 independent subject/content groups required"
        )
    validation = set(unique[: max(1, math.ceil(len(unique) * fraction))])
    train = [i for i, group in enumerate(groups) if group not in validation]
    holdout = [i for i, group in enumerate(groups) if group in validation]
    if len(train) < 4 or not holdout:
        raise ValueError("Insufficient training or validation images after grouping")
    return train, holdout


def predictions(checkpoint: RatingCheckpoint, features: NDArray[np.float64]) -> NDArray[np.float64]:
    normalized = (features - np.asarray(checkpoint.mean)) / np.asarray(checkpoint.scale)
    return np.asarray(
        normalized @ np.asarray(checkpoint.coefficients) + checkpoint.intercept, dtype=np.float64
    )


def train(
    features: list[list[float]],
    ratings: list[float],
    groups: list[str],
    *,
    alpha: float,
    seed: int,
    validation_fraction: float,
    rating_min: float,
    rating_max: float,
    snapshot_sha256: str,
    check: Callable[[], None],
    extractor: str = EXTRACTOR,
) -> tuple[RatingCheckpoint, dict[str, float | int], list[int], list[int]]:
    if not 0 < alpha <= 1000 or not 0.1 <= validation_fraction <= 0.4:
        raise ValueError("Invalid training configuration")
    matrix = np.asarray(features, dtype=np.float64)
    scores = np.asarray(ratings, dtype=np.float64)
    if (
        matrix.shape != (len(ratings), dimension(extractor))
        or len(groups) != len(ratings)
        or len(ratings) > 500
    ):
        raise ValueError("Invalid training dimensions")
    if (
        not np.isfinite(matrix).all()
        or not np.isfinite(scores).all()
        or np.any(scores < rating_min)
        or np.any(scores > rating_max)
    ):
        raise ValueError("Invalid features or ratings")
    training, validation = split_groups(groups, seed, validation_fraction)
    check()
    x, y = matrix[training], scores[training]
    if float(np.ptp(y)) == 0:
        raise ValueError("Training ratings need at least two distinct scores")
    mean = x.mean(axis=0)
    scale = np.maximum(x.std(axis=0), 0.05)
    normalized = (x - mean) / scale
    intercept = float(y.mean())
    # Dual ridge avoids an expensive dimension x dimension solve on a small dataset.
    coefficients = normalized.T @ np.linalg.solve(
        normalized @ normalized.T + alpha * np.eye(len(training)), y - intercept
    )
    check()
    state = dict(
        snapshot_sha256=snapshot_sha256,
        mean=mean.tolist(),
        scale=scale.tolist(),
        coefficients=coefficients.tolist(),
        intercept=intercept,
        rating_min=rating_min,
        rating_max=rating_max,
    )
    checkpoint: RatingCheckpoint
    if extractor == EXTRACTOR:
        checkpoint = RidgeCheckpoint.model_validate(state)
    else:
        checkpoint = PretrainedRidgeCheckpoint.model_validate(
            {**state, "representation": manifest(extractor)}
        )
    raw = predictions(checkpoint, matrix[validation])
    displayed = np.clip(raw, rating_min, rating_max)
    expected = scores[validation]
    metrics: dict[str, float | int] = {
        "labeled_images": len(ratings),
        "training_images": len(training),
        "validation_images": len(validation),
        "training_groups": len({groups[i] for i in training}),
        "validation_groups": len({groups[i] for i in validation}),
        "validation_mae": float(np.mean(np.abs(displayed - expected))),
        "validation_rmse": float(np.sqrt(np.mean((displayed - expected) ** 2))),
        "raw_validation_mae": float(np.mean(np.abs(raw - expected))),
        "mean_baseline_mae": float(np.mean(np.abs(intercept - expected))),
        "mean_baseline_rmse": float(np.sqrt(np.mean((intercept - expected) ** 2))),
    }
    check()
    return checkpoint, metrics, training, validation


class PersonalRatingEngine(ScoringEngine):
    def __init__(
        self,
        checkpoint: RatingCheckpoint,
        version: str,
        root: Path = Path("/var/lib/auvylen/models/pretrained"),
        features: list[float] | None = None,
    ):
        self.checkpoint = checkpoint
        self.version = version
        self.root, self.features = root, features

    def preprocess(self, payload: bytes) -> bytes:
        return payload

    def predict(self, prepared: bytes) -> float:
        features = self.features
        if features is None:
            features = create_extractor(self.checkpoint.extractor, self.root).extract_batch(
                [prepared]
            )[0]
        value = predictions(self.checkpoint, np.asarray([features], dtype=np.float64))[0]
        return float(value)

    def normalize(self, raw_score: float) -> float:
        return min(self.checkpoint.rating_max, max(self.checkpoint.rating_min, raw_score))

    def metadata(self) -> EngineMetadata:
        return rating_metadata(
            self.version, self.checkpoint.snapshot_sha256, self.checkpoint.extractor
        )


def baseline_metadata(version: str, snapshot_sha256: str) -> EngineMetadata:
    return EngineMetadata(
        slug="custom",
        display_name="Personal visual rating baseline",
        version=version,
        licensing_status="first_party_code_numpy_BSD_Pillow_MIT_CMU_no_external_weights",
        provenance=(
            f"{IMPLEMENTATION}; {EXTRACTOR}; owner-authorized numerical ratings; "
            f"snapshot {snapshot_sha256}"
        ),
        commercial_allowed=False,
        research_allowed=True,
        production_enabled=True,
        synthetic=False,
    )


def rating_metadata(version: str, snapshot_sha256: str, extractor: str) -> EngineMetadata:
    dimension(extractor)
    if extractor == EXTRACTOR:
        return baseline_metadata(version, snapshot_sha256)
    return EngineMetadata(
        slug="custom",
        display_name="Personal rating model with pretrained MobileNetV3-Small",
        version=version,
        licensing_status="MobileNetV3_timm_Apache_2.0_ONNX_Runtime_MIT_research_only",
        provenance=(
            f"{IMPLEMENTATION}; {MOBILENET}; "
            f"weights {manifest(MOBILENET)['weight_sha256']}; snapshot {snapshot_sha256}"
        ),
        commercial_allowed=False,
        research_allowed=True,
        production_enabled=True,
        synthetic=False,
    )
