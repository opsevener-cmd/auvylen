"""Development-only comparison of native head variants. Never reads sealed test labels.

Reuses native_dev_study's exclusion: the fixed seed-42 sealed test subjects are removed by
subject identifier before any rating is parsed. All variants are scored on identical outer
subject-grouped folds of the remaining development subjects, so differences are paired.

Variants (features are computed once; augmented views only ever enter training folds):

* ``handcrafted-A`` / ``mobilenet-A``: original single-split selector, alpha in {.01,1,100}.
* ``handcrafted-B`` / ``mobilenet-B``: grouped-CV selector over the 15-point grid.
* ``mobilenet-flip-B``: adds a horizontally mirrored training view and averages the
  prediction over the image and its mirror. A mirror is label-preserving for a frontal
  portrait; this tests whether that symmetry helps a 60-80 image regression.
* ``fusion-B``: concatenated handcrafted + MobileNet features, grouped-CV selector.

Output is aggregate only. Results describe this small development set, not accuracy on
new people, and are not a release claim.
"""

import argparse
import json
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from aevyra_inference.aesthetic import spearman
from aevyra_inference.extractors import BASELINE, MOBILENET, create_extractor
from aevyra_inference.native import Array, metrics
from aevyra_inference.native_data import Collection, load_rows, perturb
from aevyra_inference.native_dev_study import (
    HOLDOUT_SEED,
    development_table,
    paired_bootstrap,
    protocol_a,
    protocol_b,
)
from aevyra_inference.native_selection import grouped_folds
from aevyra_inference.native_train import features


def mirror(payload: bytes) -> bytes:
    with Image.open(BytesIO(payload)) as image:
        rgb = (
            ImageOps.exif_transpose(image).convert("RGB").transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        )
        out = BytesIO()
        rgb.save(out, "PNG")
        return out.getvalue()


def encode(payloads: list[bytes], name: str, root: Path) -> dict[str, Array]:
    extractor = create_extractor(name, root)
    return {
        "clean": features(payloads, extractor),
        "lighting": features((perturb(p, "lighting") for p in payloads), extractor),
        "crop": features((perturb(p, "crop") for p in payloads), extractor),
        "mirror": features((mirror(p) for p in payloads), extractor),
    }


def study(
    labels: Path,
    images: Path,
    plan: Collection,
    encoder_root: Path,
    *,
    outer_repeats: int = 5,
    seed: int = 42,
    draws: int = 2000,
) -> dict[str, Any]:
    if outer_repeats < 1 or draws < 1:
        raise ValueError("Positive repeat and bootstrap counts required")
    with tempfile.TemporaryDirectory(prefix="native-exp-") as temporary:
        dev_labels = Path(temporary) / "development.csv"
        sizes = development_table(labels, HOLDOUT_SEED, dev_labels)
        payloads, subjects, y, _, _ = load_rows(dev_labels, images, plan)
    top = float(plan.rating_max)
    started = time.perf_counter()
    hand, mobile = (
        encode(payloads, BASELINE, encoder_root),
        encode(payloads, MOBILENET, encoder_root),
    )
    fused = {k: np.concatenate([hand[k], mobile[k]], axis=1) for k in hand}
    extraction = time.perf_counter() - started
    original = ("lighting", "crop")
    variants: dict[str, tuple[Any, dict[str, Array], tuple[str, ...], bool]] = {
        "handcrafted-A": (protocol_a, hand, original, False),
        "handcrafted-B": (protocol_b, hand, original, False),
        "mobilenet-A": (protocol_a, mobile, original, False),
        "mobilenet-B": (protocol_b, mobile, original, False),
        "mobilenet-flip-B": (protocol_b, mobile, (*original, "mirror"), True),
        "fusion-B": (protocol_b, fused, original, False),
    }
    runs: dict[str, list[Array]] = {name: [] for name in [*variants, "train-mean"]}
    alphas: dict[str, list[float]] = {name: [] for name in variants}
    for repeat in range(outer_repeats):
        predicted = {name: np.empty(len(y)) for name in runs}
        for train, held in grouped_folds(subjects, 5, seed=seed + 1000 + repeat):
            inner = [subjects[i] for i in train]
            for name, (protocol, matrix, kinds, tta) in variants.items():
                views = np.stack([matrix[k][train] for k in kinds])
                head, alpha = protocol(matrix["clean"][train], views, y[train], inner, seed, top)
                value = head.predict(matrix["clean"][held])
                if tta:
                    value = (value + head.predict(matrix["mirror"][held])) / 2
                predicted[name][held] = value
                alphas[name].append(alpha)
            predicted["train-mean"][held] = y[train].mean()
        for name in runs:
            runs[name].append(predicted[name])
    errors = {k: np.mean([np.abs(p - y) for p in v], axis=0) for k, v in runs.items()}
    summary: dict[str, Any] = {}
    for name, values in runs.items():
        scores = [metrics(p, y) for p in values]
        summary[name] = {
            "mae": float(np.mean([s["mae"] for s in scores])),
            "rmse": float(np.mean([s["rmse"] for s in scores])),
            "spearman": None
            if name == "train-mean"
            else (
                None
                if any(s["spearman"] is None for s in scores)
                else float(np.mean([s["spearman"] for s in scores]))
            ),
            "repeat_averaged_spearman": None
            if name == "train-mean"
            else spearman(np.mean(values, axis=0), y),
            "mae_sd_across_repeats": float(np.std([s["mae"] for s in scores])),
        }
        if name in alphas:
            summary[name]["selected_alpha_counts"] = {
                str(a): alphas[name].count(a) for a in sorted(set(alphas[name]))
            }
    reference = "mobilenet-A"  # The current pilot candidate's architecture and selector.
    return {
        "policy": (
            "sealed seed-42 test subjects removed before ratings were parsed; paired outer "
            "subject-grouped CV over development subjects only; no test metric computed"
        ),
        **sizes,
        "development_subjects": len(set(subjects)),
        "outer": f"repeated subject-grouped 5-fold x {outer_repeats}",
        "variants": summary,
        "paired_mae_vs_train_mean": {
            name: paired_bootstrap(errors["train-mean"], errors[name], subjects, draws, 20261107)
            for name in variants
        },
        f"paired_mae_vs_{reference}": {
            name: paired_bootstrap(errors[reference], errors[name], subjects, draws, 20261107)
            for name in variants
            if name != reference
        },
        "interval_scope": (
            "descriptive resampling of fixed out-of-fold errors; no refitting, split, "
            "selection or rater uncertainty; negative favours the variant"
        ),
        "seconds": {"feature_extraction": extraction},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("labels", "images", "plan", "encoder-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--outer-repeats", type=int, default=5)
    args = parser.parse_args()
    try:
        plan = Collection.model_validate_json(args.plan.read_bytes())
        if plan.synthetic:
            raise ValueError("Experiments require genuine human labels")
        result = study(
            args.labels, args.images, plan, args.encoder_root, outer_repeats=args.outer_repeats
        )
    except (OSError, ValueError) as exc:
        print(f"Development experiment refused: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
