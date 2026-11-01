"""Evaluate a fixed, saved London pilot; reproduce heads without test-based selection."""

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from aevyra_inference.aesthetic import split_by_subject
from aevyra_inference.extractors import create_extractor
from aevyra_inference.native import fit_head, metrics
from aevyra_inference.native_checkpoint import load, pack
from aevyra_inference.native_data import load_rows, perturb
from aevyra_inference.native_train import features
from aevyra_inference.native_uncertainty import uncertainty


def evaluate(root: Path, checkpoint: Path, pin: str, encoder_root: Path) -> dict[str, Any]:
    saved, item = load(checkpoint, pin, require_release=False)
    if item.collection.synthetic:
        raise ValueError("Human pilot evaluation refuses synthetic checkpoints")
    payloads, subjects, y, _, digest = load_rows(
        root / "means.csv", root / "images", item.collection
    )
    if digest != item.collection_sha256:
        raise ValueError("Evaluation collection changed")
    train, val, test = split_by_subject(subjects, item.report["seed"])
    metadata = json.loads((root / "subject-metadata.json").read_text())
    baseline = np.full(len(test), y[train].mean())
    median = np.full(len(test), np.median(y[train]))
    result: dict[str, Any] = {
        "mean_baseline": {
            **metrics(baseline, y[test]),
            "uncertainty": uncertainty(baseline, y[test], [subjects[i] for i in test], baseline),
        },
        "median_baseline": {
            **metrics(median, y[test]),
            "uncertainty": uncertainty(median, y[test], [subjects[i] for i in test], baseline),
        },
        "encoders": {},
        "selected_encoder_frozen": item.encoder,
        "test_subjects": len(test),
        "collection_sha256": digest,
        "native_scale": list(item.native_scale),
        "first_holdout_image_selection": (
            "first test row in fixed subject-hash split; no outcome-based selection"
        ),
    }
    for encoder in sorted(item.report["encoder_comparison"]):
        started = time.perf_counter()
        extractor = create_extractor(encoder, encoder_root)
        clean = features(payloads, extractor)
        views = [
            features((perturb(payloads[i], kind) for i in train), extractor)
            for kind in ("lighting", "crop")
        ]
        choices = [c for c in item.report["selection"] if c["encoder"] == encoder]
        alpha = min(choices, key=lambda c: (c["validation"]["mae"], c["alpha"]))["alpha"]
        head = fit_head(
            np.concatenate([clean[train], *views]),
            np.tile(y[train], 3),
            alpha,
            item.collection.rating_max,
        )
        if encoder == item.encoder and pack(head) != pack(saved):
            raise ValueError("Exact-protocol winner reproduction differs from saved weights")
        predicted = head.predict(clean[test])
        subgroups: dict[str, dict[str, Any]] = {}
        for trait in ("sex", "ethnicity", "age_band"):
            subgroups[trait] = {}
            for group in sorted({metadata[subjects[i]][trait] for i in test}):
                indices = np.asarray(
                    [j for j, i in enumerate(test) if metadata[subjects[i]][trait] == group],
                    dtype=int,
                )
                n = len(indices)
                subgroups[trait][group] = {
                    "n": n,
                    "metrics": metrics(predicted[indices], y[test][indices]) if n >= 5 else None,
                    "uncertainty": uncertainty(
                        predicted[indices],
                        y[test][indices],
                        [subjects[test[j]] for j in indices],
                        baseline[indices],
                    )
                    if n >= 5
                    else None,
                }
        result["encoders"][encoder] = {
            **metrics(predicted, y[test]),
            "selected_alpha_from_original_validation": alpha,
            "uncertainty": uncertainty(predicted, y[test], [subjects[i] for i in test], baseline),
            "subgroups": subgroups,
            "extraction_and_exact_head_reproduction_seconds": time.perf_counter() - started,
            "winner_weight_bytes_identical": True if encoder == item.encoder else None,
        }
    # Private selection file contains a path, never copied to public report.
    with (root / "inspection-input.json").open("x") as f:
        (root / "inspection-input.json").chmod(0o600)
        json.dump({"image": str(root / "images" / f"{subjects[test[0]]}_03.jpg")}, f)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("root", "checkpoint", "encoder-root"):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    a = p.parse_args()
    print(
        json.dumps(
            evaluate(a.root, a.checkpoint, a.manifest_sha256, a.encoder_root),
            indent=2,
            allow_nan=False,
        )
    )
