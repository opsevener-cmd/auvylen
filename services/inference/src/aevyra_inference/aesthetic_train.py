"""Operator-only training for the aesthetic rating-distribution model.

Runs offline in an approved remote environment, never in a web request. Inputs:

* ``--labels``: CSV with exactly ``image,subject_id,votes_1,votes_2,votes_3,votes_4,votes_5``.
  Vote columns are integer counts of real human ratings. Mean-score-only labels are refused:
  a distribution is never manufactured from a mean.
* ``--images``: directory containing the referenced JPEG/PNG files.
* ``--plan``: JSON authorization evidence (see ``DatasetEvidence``) kept in private storage.

The command publishes a new immutable checkpoint and prints its manifest SHA-256 and the
release-gate result. It never prints image paths, subject identifiers or votes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from pydantic import ValidationError

from aevyra_inference.aesthetic import RATING_BINS, SEED, fit_scoring_head
from aevyra_inference.aesthetic_checkpoint import (
    DatasetEvidence,
    release_failures,
    write_checkpoint,
)
from aevyra_inference.extractors import BATCH_SIZE, create_extractor, dimension

COLUMNS = ["image", "subject_id", *(f"votes_{k}" for k in range(1, RATING_BINS + 1))]
MAX_IMAGES = 100_000
MAX_IMAGE_BYTES = 10 * 1024 * 1024


class LabelError(ValueError):
    pass


def read_labels(
    labels: Path, images: Path, *, min_votes: int
) -> tuple[list[Path], list[str], np.ndarray]:
    root = images.resolve()
    paths: list[Path] = []
    subjects: list[str] = []
    votes: list[list[int]] = []
    with labels.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != COLUMNS:
            raise LabelError(
                "Labels need exactly image,subject_id,votes_1..votes_5 real vote counts"
            )
        for line, row in enumerate(reader, start=2):
            if len(paths) >= MAX_IMAGES:
                raise LabelError("Too many labelled images")
            path = (root / row["image"]).resolve()
            if not path.is_relative_to(root) or path.is_symlink() or not path.is_file():
                raise LabelError(f"Line {line}: image missing or outside the image directory")
            subject = row["subject_id"].strip()
            if not subject or len(subject) > 200:
                raise LabelError(f"Line {line}: subject identifier required")
            try:
                counts = [int(row[f"votes_{k}"]) for k in range(1, RATING_BINS + 1)]
            except (TypeError, ValueError):
                raise LabelError(f"Line {line}: votes must be integer counts") from None
            if any(c < 0 for c in counts) or sum(counts) < min_votes:
                raise LabelError(f"Line {line}: needs at least {min_votes} real ratings")
            paths.append(path)
            subjects.append(subject)
            votes.append(counts)
    if len(set(paths)) != len(paths):
        raise LabelError("Duplicate image rows")
    return paths, subjects, np.asarray(votes, dtype=np.float64)


def extract_features(paths: list[Path], extractor_id: str, pretrained_root: Path) -> np.ndarray:
    extractor = create_extractor(extractor_id, pretrained_root)
    seen: dict[str, int] = {}
    rows: list[list[float]] = []
    for start in range(0, len(paths), BATCH_SIZE):
        payloads = []
        for index, path in enumerate(paths[start : start + BATCH_SIZE], start=start):
            if path.stat().st_size > MAX_IMAGE_BYTES:
                raise LabelError("Image exceeds 10 MiB")
            payload = path.read_bytes()
            # File metadata or PNG encoding differences must not conceal identical pixels.
            with Image.open(BytesIO(payload), formats=["JPEG", "PNG"]) as image:
                if max(image.size) > 4096 or image.width * image.height > 16_000_000:
                    raise LabelError("Image dimensions exceed training limits")
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                digest = hashlib.sha256(
                    str(normalized.size).encode() + normalized.tobytes()
                ).hexdigest()
            if digest in seen:
                # Identical bytes under two rows would leak across subject splits.
                raise LabelError(f"Rows {seen[digest] + 2} and {index + 2} are identical images")
            seen[digest] = index
            payloads.append(payload)
        rows.extend(extractor.extract_batch(payloads))
    matrix = np.asarray(rows, dtype=np.float64)
    if matrix.shape != (len(paths), dimension(extractor_id)) or not np.isfinite(matrix).all():
        raise ValueError("Invalid extracted features")
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--extractor", default="mobilenetv3-small-imagenet-onnx-v1")
    parser.add_argument("--pretrained-root", type=Path)
    parser.add_argument("--min-votes", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=0.003)
    parser.add_argument("--weight-decay", type=float, default=0.0005)
    parser.add_argument("--epochs", type=int, default=250)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    if args.min_votes < 1:
        parser.error("--min-votes must be positive")
    try:
        dataset = DatasetEvidence.model_validate_json(args.plan.read_bytes())
    except (OSError, ValidationError):
        print(
            "Authorization plan missing or invalid; see docs/aesthetic-scoring.md", file=sys.stderr
        )
        return 2
    try:
        paths, subjects, votes = read_labels(args.labels, args.images, min_votes=args.min_votes)
        started = time.monotonic()
        features = extract_features(
            paths, args.extractor, args.pretrained_root or args.model_root / "pretrained"
        )
        extraction_seconds = time.monotonic() - started
        head, metrics = fit_scoring_head(
            features,
            votes,
            subjects,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            epochs=args.epochs,
            patience=args.patience,
            seed=args.seed,
        )
    except LabelError as exc:
        print(f"Training refused: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(
            f"Training refused: {type(exc).__name__}; verify labels and image inputs",
            file=sys.stderr,
        )
        return 1
    totals = votes.sum(axis=1)
    training = {
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "epochs": args.epochs,
        "patience": args.patience,
        "seed": args.seed,
        "min_votes": args.min_votes,
        "votes_per_image_min": int(totals.min()),
        "votes_per_image_median": float(np.median(totals)),
        "extraction_seconds": extraction_seconds,
        "fit_seconds": time.monotonic() - started - extraction_seconds,
        "labels_sha256": hashlib.sha256(args.labels.read_bytes()).hexdigest(),
    }
    item, sha256 = write_checkpoint(
        args.model_root,
        head,
        model_version=args.model_version,
        extractor=args.extractor,
        dataset=dataset,
        training=training,
        metrics=metrics,
    )
    failures = release_failures(item)
    summary = {
        "model_version": item.model_version,
        "manifest_sha256": sha256,
        "release_gate": "passed" if not failures else "failed",
        "release_failures": failures,
        "metrics": {k: v for k, v in item.metrics.items() if k != "split"},
        "calibration": item.calibration.model_dump(),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
