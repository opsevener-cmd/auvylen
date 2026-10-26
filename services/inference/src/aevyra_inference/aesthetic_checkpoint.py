"""Immutable, integrity-verified checkpoints and the release gate for the aesthetic model.

Layout: ``<model_root>/aesthetic/<model_version>/{manifest.json,head.f64}``. The head is raw
little-endian float64 (mean, scale, weights, bias) so loading never parses pickles or zips.
The operator pins the exact manifest SHA-256; the manifest pins the weight SHA-256 and
the exact feature-extractor manifest. Any mismatch reports unavailable, never a score.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Literal

import numpy as np
from aevyra_contracts import EngineMetadata
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from aevyra_inference.aesthetic import CALIBRATION_LEVEL, RATING_BINS, ScoringHead, analyze
from aevyra_inference.engine import ScoringEngine
from aevyra_inference.extractors import dimension, manifest

SLUG = "auvylen-aesthetic"
FORMAT: Final = "auvylen-aesthetic-checkpoint-v1"
IMPLEMENTATION: Final = "aesthetic-distribution-head-v1"
WEIGHTS_FILE: Final = "head.f64"
MANIFEST_FILE = "manifest.json"
MAX_MANIFEST_BYTES = 1024 * 1024
VERSION_PATTERN = r"^[a-z0-9][a-z0-9.-]{0,63}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
# Minimum engineering gates for enabling user-facing scoring. Passing them is necessary,
# not sufficient: they do not establish scientific validity or a commercial licence.
GATE_MIN_TEST_SUBJECTS = 10
GATE_MIN_TEST_IMAGES = 30
GATE_MIN_SPEARMAN = 0.3
GATE_COVERAGE_TOLERANCE = 0.1

Text = Annotated[str, Field(min_length=1, max_length=500)]


class DatasetEvidence(BaseModel):
    """Operator-recorded authorization; no field here is inferred from images."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    name: Text
    license: Text
    terms_url: Text
    authorization_reference: Text
    reviewer: Text
    annotator_population: Text
    adult_subjects_confirmed: Literal[True]
    rating_scale: Literal["five ordered categories, 1 (lowest) to 5 (highest)"]
    commercial_use_permitted: bool = False
    synthetic: bool = False


class Calibration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str = Field(min_length=1, max_length=100)
    method: str
    level: float = Field(gt=0, lt=1)
    validation_n: int = Field(ge=0)
    half_width_display: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    test_coverage: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class AestheticManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["auvylen-aesthetic-checkpoint-v1"] = FORMAT
    implementation: Literal["aesthetic-distribution-head-v1"] = IMPLEMENTATION
    model_version: str = Field(pattern=VERSION_PATTERN)
    created_at: str
    extractor: str
    representation: dict[str, JsonValue]
    feature_dimension: int = Field(ge=1)
    rating_bins: Literal[5] = 5
    weights_file: Literal["head.f64"] = WEIGHTS_FILE
    weights_sha256: str = Field(pattern=SHA256_PATTERN)
    weights_bytes: int = Field(ge=1)
    dataset: DatasetEvidence
    training: dict[str, JsonValue]
    metrics: dict[str, JsonValue]
    calibration: Calibration

    @model_validator(mode="after")
    def exact_representation(self) -> AestheticManifest:
        try:
            expected = dimension(self.extractor)
        except ValueError:
            raise ValueError("Unknown feature extractor") from None
        if self.feature_dimension != expected or self.representation != manifest(self.extractor):
            raise ValueError("Checkpoint feature extractor version mismatch")
        if self.weights_bytes != head_bytes(self.feature_dimension):
            raise ValueError("Checkpoint weight size mismatch")
        return self


def head_bytes(features: int) -> int:
    return 8 * (2 * features + features * RATING_BINS + RATING_BINS)


def serialize_head(head: ScoringHead) -> bytes:
    d = head.mean.size
    arrays = (head.mean, head.scale, head.weights, head.bias)
    shapes = ((d,), (d,), (d, RATING_BINS), (RATING_BINS,))
    if any(np.shape(a) != s for a, s in zip(arrays, shapes, strict=True)):
        raise ValueError("Invalid scoring head shape")
    data = b"".join(np.ascontiguousarray(a, dtype="<f8").tobytes() for a in arrays)
    deserialize_head(data, d)  # Never write a head that cannot be loaded back.
    return data


def deserialize_head(data: bytes, features: int) -> ScoringHead:
    if len(data) != head_bytes(features):
        raise ValueError("Checkpoint weight size mismatch")
    values = np.frombuffer(data, dtype="<f8").astype(np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Non-finite checkpoint values")
    d, k = features, RATING_BINS
    head = ScoringHead(
        mean=values[:d].copy(),
        scale=values[d : 2 * d].copy(),
        weights=values[2 * d : 2 * d + d * k].reshape(d, k).copy(),
        bias=values[2 * d + d * k :].copy(),
    )
    if np.any(head.scale <= 0):
        raise ValueError("Invalid checkpoint normalization scale")
    return head


def release_failures(item: AestheticManifest, *, allow_synthetic: bool = False) -> list[str]:
    """Reasons user-facing scoring must stay disabled. Empty only for a validated checkpoint."""
    failures = []
    metrics = item.metrics
    if item.dataset.synthetic and not allow_synthetic:
        failures.append("synthetic_dataset")

    def number(key: str) -> float | None:
        value = metrics.get(key)
        return float(value) if isinstance(value, int | float) else None

    test_subjects, test_images = number("test_subjects"), number("test_images")
    if test_subjects is None or test_subjects < GATE_MIN_TEST_SUBJECTS:
        failures.append("too_few_test_subjects")
    if test_images is None or test_images < GATE_MIN_TEST_IMAGES:
        failures.append("too_few_test_images")
    mae, baseline = number("test_mae"), number("mean_baseline_mae")
    if mae is None or baseline is None or mae >= baseline:
        failures.append("does_not_beat_mean_baseline")
    loss, loss_baseline = (
        number("test_distribution_loss"),
        number("mean_distribution_baseline_loss"),
    )
    if loss is None or loss_baseline is None or loss >= loss_baseline:
        failures.append("does_not_beat_distribution_baseline")
    correlation = number("test_spearman")
    if correlation is None or correlation < GATE_MIN_SPEARMAN:
        failures.append("insufficient_ranking_correlation")
    calibration = item.calibration
    if calibration.half_width_display is None or calibration.test_coverage is None:
        failures.append("uncalibrated")
    elif calibration.test_coverage < calibration.level - GATE_COVERAGE_TOLERANCE:
        failures.append("calibration_coverage_failed")
    return failures


def _checkpoint_dir(model_root: Path, version: str) -> Path:
    if not re.fullmatch(VERSION_PATTERN, version):
        raise ValueError("Invalid model version")
    base = (model_root / "aesthetic").resolve()
    path = base / version
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise ValueError("Invalid checkpoint path")
    return path


def _write_once(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
    except OSError:
        path.unlink(missing_ok=True)
        raise
    path.chmod(0o444)


def write_checkpoint(
    model_root: Path,
    head: ScoringHead,
    *,
    model_version: str,
    extractor: str,
    dataset: DatasetEvidence,
    training: dict[str, JsonValue],
    metrics: dict[str, Any],
) -> tuple[AestheticManifest, str]:
    """Publish a new immutable version; never overwrites. Returns the manifest SHA-256."""
    weights = serialize_head(head)
    if head.mean.size != dimension(extractor):
        raise ValueError("Feature dimension does not match the extractor")
    calibration = metrics.get("calibration", {})
    item = AestheticManifest(
        model_version=model_version,
        created_at=datetime.now(UTC).isoformat(),
        extractor=extractor,
        representation=manifest(extractor),
        feature_dimension=head.mean.size,
        weights_sha256=hashlib.sha256(weights).hexdigest(),
        weights_bytes=len(weights),
        dataset=dataset,
        training=training,
        metrics={key: value for key, value in metrics.items() if key != "calibration"},
        calibration=Calibration(
            version=f"{model_version}+split-conformal-{round(CALIBRATION_LEVEL * 100)}",
            **calibration,
        ),
    )
    encoded = (json.dumps(item.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode()
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest too large")
    directory = _checkpoint_dir(model_root, model_version)
    directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.mkdir(mode=0o700)  # FileExistsError: published versions are immutable.
    _write_once(directory / WEIGHTS_FILE, weights)
    _write_once(directory / MANIFEST_FILE, encoded)
    directory.chmod(0o500)
    return item, hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class LoadedCheckpoint:
    manifest: AestheticManifest
    manifest_sha256: str
    head: ScoringHead


def _read_bounded(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("Checkpoint file missing")
    with path.open("rb") as file:
        data = file.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Checkpoint file too large")
    return data


def load_checkpoint(
    model_root: Path, version: str, expected_manifest_sha256: str
) -> LoadedCheckpoint:
    if not re.fullmatch(SHA256_PATTERN, expected_manifest_sha256):
        raise ValueError("Invalid pinned manifest checksum")
    directory = _checkpoint_dir(model_root, version)
    raw = _read_bounded(directory / MANIFEST_FILE, MAX_MANIFEST_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
        raise ValueError("Checkpoint manifest checksum mismatch")
    try:
        item = AestheticManifest.model_validate_json(raw)
    except ValidationError:
        raise ValueError("Invalid checkpoint manifest") from None
    if item.model_version != version:
        raise ValueError("Checkpoint version mismatch")
    weights = _read_bounded(directory / WEIGHTS_FILE, item.weights_bytes)
    if hashlib.sha256(weights).hexdigest() != item.weights_sha256:
        raise ValueError("Checkpoint weight checksum mismatch")
    return LoadedCheckpoint(
        item, expected_manifest_sha256, deserialize_head(weights, item.feature_dimension)
    )


@dataclass(frozen=True)
class CheckpointStatus:
    available: bool
    reason: str
    checkpoint: LoadedCheckpoint | None = None


def checkpoint_status(
    model_root: Path,
    version: str | None,
    manifest_sha256: str | None,
    *,
    enabled: bool,
    allow_synthetic: bool = False,
) -> CheckpointStatus:
    """Reasons are fixed vocabulary; exception text is never exposed."""
    if not enabled:
        return CheckpointStatus(False, "disabled")
    if not version or not manifest_sha256:
        return CheckpointStatus(False, "checkpoint_not_configured")
    try:
        loaded = load_checkpoint(model_root, version, manifest_sha256)
    except FileNotFoundError:
        return CheckpointStatus(False, "checkpoint_missing")
    except (OSError, ValueError):
        return CheckpointStatus(False, "checkpoint_integrity_failure")
    if release_failures(loaded.manifest, allow_synthetic=allow_synthetic):
        return CheckpointStatus(False, "validation_gate_failed", loaded)
    return CheckpointStatus(True, "ready", loaded)


def engine_metadata(item: AestheticManifest, *, release_ready: bool) -> EngineMetadata:
    return EngineMetadata(
        slug=SLUG,
        display_name="Auvylen aesthetic rating-distribution model",
        version=item.model_version,
        licensing_status=(
            f"first_party_head; dataset licence: {item.dataset.license}; "
            f"extractor {item.extractor} research-only"
        )[:500],
        provenance=(
            f"{IMPLEMENTATION}; {item.extractor}; weights {item.weights_sha256}; "
            f"dataset {item.dataset.name}; authorization {item.dataset.authorization_reference}"
        )[:1000],
        # Commercial use needs separate licence evidence for dataset and extractor.
        commercial_allowed=False,
        research_allowed=True,
        production_enabled=release_ready,
        synthetic=item.dataset.synthetic,
    )


class AestheticScoringEngine(ScoringEngine):
    """Features are extracted by the caller with the checkpoint's exact extractor."""

    def __init__(self, checkpoint: LoadedCheckpoint, features: list[float], *, release_ready: bool):
        if len(features) != checkpoint.manifest.feature_dimension:
            raise ValueError("Feature dimension does not match the checkpoint")
        self.checkpoint = checkpoint
        self.features = features
        self.release_ready = release_ready

    def preprocess(self, payload: bytes) -> bytes:
        return payload

    def predict(self, prepared: bytes) -> float:
        return float(self.analysis()["expected_rating_5"])

    def normalize(self, raw_score: float) -> float:
        if not 1 <= raw_score <= 5:
            raise ValueError("Expected rating outside 1-5")
        return min(10.0, max(1.0, 1.0 + 2.25 * (raw_score - 1.0)))

    def analysis(self) -> dict[str, Any]:
        return analyze(self.checkpoint.head, np.asarray(self.features, dtype=np.float64))

    def metadata(self) -> EngineMetadata:
        return engine_metadata(self.checkpoint.manifest, release_ready=self.release_ready)
