"""Immutable native-rating artifacts. No pickle, automatic downloads or commercial gate."""

import hashlib
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from aevyra_contracts import EngineMetadata
from pydantic import BaseModel, ConfigDict, Field

from aevyra_inference.engine import ScoringEngine
from aevyra_inference.extractors import create_extractor, dimension, manifest
from aevyra_inference.native import NativeHead
from aevyra_inference.native_data import Collection
from aevyra_inference.providers import ProviderStatus

SLUG = "auvylen-native"


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format: Literal["auvylen-native-ridge-v1"] = "auvylen-native-ridge-v1"
    created_at: str
    encoder: str
    representation: dict[str, Any]
    collection: Collection
    collection_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    weights_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    report: dict[str, Any]
    native_scale: tuple[Literal[1], Literal[5]] = (1, 5)


def release_failures(item: Manifest) -> list[str]:
    r, failures = item.report, []

    def finite(value: Any) -> bool:
        if isinstance(value, dict):
            return all(finite(v) for v in value.values())
        if isinstance(value, list):
            return all(finite(v) for v in value)
        return not isinstance(value, float) or math.isfinite(value)

    if not finite(r):
        failures.append("nonfinite_evaluation")
    if item.collection.synthetic:
        failures.append("synthetic_data")
    try:
        if r["test"]["n"] < 30 or r["subject_counts"]["test"] < 10:
            failures.append("insufficient_test_subjects")
        if not 0 <= r["test"]["mae"] < min(r["mean_baseline"]["mae"], r["median_baseline"]["mae"]):
            failures.append("does_not_beat_baselines")
        correlation = r["test"]["spearman"]
        if correlation is None or not 0.3 <= correlation <= 1:
            failures.append("weak_rank_correlation")
        if not r.get("pose_review_reference"):
            failures.append("real_pose_review_missing")
        if not r.get("cohorts") or any(
            c["n"] < 10 or c["subjects"] < 5 for c in r["cohorts"].values()
        ):
            failures.append("cohort_review_underpowered")
        if any(v["mean_absolute_drift"] > 0.3 for v in r["perturbations"].values()):
            failures.append("photographic_sensitivity")
        if set(r["perturbations"]) != {"lighting", "crop", "rotation"}:
            failures.append("robustness_evaluation_missing")
    except (KeyError, TypeError, ValueError):
        failures.append("incomplete_evaluation")
    return failures


def pack(head: NativeHead) -> bytes:
    return (
        np.concatenate([head.mean, head.scale, head.weights, [head.intercept]])
        .astype("<f8")
        .tobytes()
    )


def write(root: Path, head: NativeHead, item: Manifest) -> str:
    if root.exists():
        raise ValueError("Checkpoint directory must be new and immutable")
    raw = pack(head)
    if hashlib.sha256(raw).hexdigest() != item.weights_sha256:
        raise ValueError("Head hash mismatch")
    encoded_manifest = item.model_dump_json(indent=2).encode()
    if len(encoded_manifest) > 1024 * 1024:
        raise ValueError("Checkpoint provenance exceeds manifest limit")
    root.mkdir(parents=True, mode=0o700)
    for name, data in [
        ("head.f64", raw),
        ("manifest.json", encoded_manifest),
    ]:
        with (root / name).open("xb") as f:
            os.chmod(root / name, 0o600)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    return hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()


def load(root: Path, pin: str, *, require_release: bool = True) -> tuple[NativeHead, Manifest]:
    path = root / "manifest.json"
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Invalid manifest")
    data = path.read_bytes()
    if len(pin) != 64 or hashlib.sha256(data).hexdigest() != pin:
        raise ValueError("Manifest hash mismatch")
    item = Manifest.model_validate_json(data)
    if item.representation != manifest(item.encoder):
        raise ValueError("Encoder provenance mismatch")
    if require_release and release_failures(item):
        raise ValueError("Native model has not passed release review")
    d = dimension(item.encoder)
    weights = root / "head.f64"
    if weights.is_symlink() or weights.stat().st_size != 8 * (3 * d + 1):
        raise ValueError("Invalid head bytes")
    raw = weights.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item.weights_sha256:
        raise ValueError("Head hash mismatch")
    v = np.frombuffer(raw, dtype="<f8").copy()
    if not np.isfinite(v).all() or np.any(v[d : 2 * d] <= 0):
        raise ValueError("Invalid head values")
    return NativeHead(v[:d], v[d : 2 * d], v[2 * d : 3 * d], float(v[-1])), item


class NativeEngine(ScoringEngine):
    def __init__(self, root: Path, encoder_root: Path):
        self.pin = os.environ.get("AUVYLEN_NATIVE_MANIFEST_SHA256", "")
        self.head, self.item = load(root, self.pin)
        self.encoder = create_extractor(self.item.encoder, encoder_root)

    def preprocess(self, payload: bytes) -> bytes:
        return payload

    def predict(self, prepared: bytes) -> float:
        features = np.asarray(self.encoder.extract_batch([prepared]), dtype=np.float64)
        return float(self.head.predict(features)[0])

    def normalize(self, raw_score: float) -> float:
        return raw_score  # Native 1–5, no 1–10 conversion or interval claim.

    def metadata(self) -> EngineMetadata:
        return EngineMetadata(
            slug=SLUG,
            display_name="Auvylen Native Rating",
            version=self.pin,
            licensing_status="reviewed non-commercial research",
            provenance="Auvylen native ridge v1; encoder and collection hashes pinned",
            commercial_allowed=False,
            research_allowed=True,
            production_enabled=False,
            synthetic=False,
        )


class NativeProvider:
    def availability(self, model_root: Path) -> ProviderStatus:
        try:
            _, item = load(model_root, os.environ.get("AUVYLEN_NATIVE_MANIFEST_SHA256", ""))
            from aevyra_inference.extractors import availability

            ready, _ = availability(item.encoder, model_root.parent / "pretrained")
            return ProviderStatus(
                SLUG, "Auvylen Native Rating", ready, "ready" if ready else "missing_weights"
            )
        except (OSError, ValueError):
            return ProviderStatus(SLUG, "Auvylen Native Rating", False, "missing_weights")

    def load(self, model_root: Path) -> ScoringEngine:
        return NativeEngine(model_root, model_root.parent / "pretrained")


def new_manifest(
    encoder: str, collection: Collection, digest: str, head: NativeHead, report: dict[str, Any]
) -> Manifest:
    return Manifest(
        created_at=datetime.now(UTC).isoformat(),
        encoder=encoder,
        representation=manifest(encoder),
        collection=collection,
        collection_sha256=digest,
        weights_sha256=hashlib.sha256(pack(head)).hexdigest(),
        report=report,
    )
