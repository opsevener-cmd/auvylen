"""Development-only comparison of ridge-selection protocols. Never reads sealed test labels.

Sealed test subjects (the fixed seed-42 subject-hash test partition) are removed from the
label table by subject identifier before any rating is parsed or any image is loaded. The
remaining development subjects (train + validation) are evaluated with nested, repeated
subject-grouped cross-validation:

* Protocol A ("validation-3"): the original rule, one inner subject-hash validation split
  holding ~25% of outer-training subjects, penalties {.01, 1, 100}.
* Protocol B ("grouped-cv"): inner repeated grouped 5-fold CV over a 15-point log grid.

Both fit training-only standardization with the original train-only augmentation views,
and both are scored on identical outer held-out subjects. Output is aggregate only.
"""

import argparse
import csv
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from aevyra_inference.aesthetic import spearman, split_by_subject
from aevyra_inference.extractors import create_extractor
from aevyra_inference.native import ALPHAS, Array, fit_head, metrics
from aevyra_inference.native_data import Collection, load_rows, perturb
from aevyra_inference.native_selection import ALPHA_GRID, cv_curve, grouped_folds, select_alpha
from aevyra_inference.native_train import features

COLUMNS = ["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"]
HOLDOUT_SEED = 42
# SHA-256 of newline-joined, sorted IDs from the pinned adult London metadata.
# Subsetting/replacing the input universe must not redefine the sealed 20 people.
LONDON_SUBJECTS_SHA256 = "c2d37370bbcdeab00048dbaa686caff075609506d641a444221f24f480d377ff"


def development_table(labels: Path, seed: int, destination: Path) -> dict[str, int]:
    """Copy only development rows. Test rows are dropped by subject id, ratings unparsed."""
    if seed != HOLDOUT_SEED:
        raise ValueError("The sealed London holdout uses seed 42 and cannot be changed")
    with labels.open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader)
        if header != COLUMNS:
            raise ValueError("Unexpected native label columns")
        rows = list(reader)
    subjects = [row[1].strip() for row in rows]
    if (
        hashlib.sha256("\n".join(sorted(set(subjects))).encode()).hexdigest()
        != LONDON_SUBJECTS_SHA256
    ):
        raise ValueError("The fixed adult London subject registry changed")
    train, val, test = split_by_subject(subjects, seed)
    sealed = {subjects[i] for i in test}
    with destination.open("x", newline="", encoding="utf-8") as file:
        destination.chmod(0o600)
        writer = csv.writer(file)
        writer.writerow(COLUMNS)
        writer.writerows(row for row in rows if row[1].strip() not in sealed)
    return {
        "development_images": len(train) + len(val),
        "sealed_test_subjects_excluded": len(sealed),
    }


def checked_development_rows(labels: Path, subject_registry: Path) -> list[dict[str, str]]:
    """Validate a precomputed London development table before any label/image is consumed.

    The registry contains subject identifiers only for this check; no sealed labels are read.
    An arbitrary filename called development.csv is not itself an exclusion guarantee.
    """
    registry = json.loads(subject_registry.read_bytes())
    if (
        not isinstance(registry, dict)
        or hashlib.sha256("\n".join(sorted(registry)).encode()).hexdigest()
        != LONDON_SUBJECTS_SHA256
    ):
        raise ValueError("The fixed adult London subject registry changed")
    subjects = sorted(registry)
    train, val, _ = split_by_subject(subjects, HOLDOUT_SEED)
    allowed = {subjects[i] for i in [*train, *val]}
    with labels.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != COLUMNS:
            raise ValueError("Unexpected native label columns")
        rows = list(reader)
    if (
        len(rows) != len(allowed)
        or {row["subject_id"] for row in rows} != allowed
        or any(row["image"] != row["subject_id"] + "_03.jpg" for row in rows)
    ):
        raise ValueError(
            "Only the fixed development subjects and their declared portraits are allowed"
        )
    return rows


def inner_validation_split(subjects: list[str], seed: int) -> tuple[list[int], list[int]]:
    """Protocol A's single subject-hash split: ~25% of subjects validate (20 of the 80)."""
    unique = sorted(set(subjects), key=lambda s: hashlib.sha256(f"{seed}:{s}".encode()).digest())
    held = set(unique[: max(1, round(len(unique) * 0.25))])
    return (
        [i for i, s in enumerate(subjects) if s not in held],
        [i for i, s in enumerate(subjects) if s in held],
    )


def augmented(x: Array, views: Array, rows: list[int] | np.ndarray) -> tuple[Array, int]:
    return np.concatenate([x[rows], *views[:, rows]]), len(views) + 1


def protocol_a(x: Array, views: Array, y: Array, subjects: list[str], seed: int, top: float) -> Any:
    fit, val = inner_validation_split(subjects, seed)
    candidates = []
    for alpha in ALPHAS:
        tx, copies = augmented(x, views, fit)
        head = fit_head(tx, np.tile(y[fit], copies), alpha, top)
        candidates.append((float(np.abs(head.predict(x[val]) - y[val]).mean()), alpha))
    alpha = min(candidates)[1]  # Original tie-break order: (MAE, alpha).
    tx, copies = augmented(x, views, list(range(len(y))))
    return fit_head(tx, np.tile(y, copies), alpha, top), alpha


def protocol_b(x: Array, views: Array, y: Array, subjects: list[str], seed: int, top: float) -> Any:
    curve = cv_curve(x, y, subjects, rating_max=top, seed=seed, views=views)
    alpha = select_alpha(curve)
    tx, copies = augmented(x, views, list(range(len(y))))
    return fit_head(tx, np.tile(y, copies), alpha, top), alpha


def paired_bootstrap(
    first: Array, second: Array, subjects: list[str], draws: int, seed: int
) -> dict[str, float]:
    """Descriptive cluster resampling of fixed OOF errors, not full training uncertainty.

    Overlapping outer training folds make these errors dependent. The interval does not
    account for model refitting, split or selection variability, or rater uncertainty.
    """
    unique = sorted(set(subjects))
    groups = [np.flatnonzero(np.asarray(subjects) == s) for s in unique]
    difference = second - first
    rng = np.random.default_rng(seed)
    values = [
        float(np.mean(np.concatenate([difference[groups[i]] for i in picks])))
        for picks in (rng.integers(0, len(groups), len(groups)) for _ in range(draws))
    ]
    return {
        "mean": float(difference.mean()),
        "low": float(np.quantile(values, 0.025)),
        "high": float(np.quantile(values, 0.975)),
        "share_of_draws_favouring_b": float(np.mean(np.asarray(values) < 0)),
    }


def study(
    labels: Path,
    images: Path,
    plan: Collection,
    encoder_root: Path,
    encoders: list[str],
    *,
    seed: int = 42,
    outer_repeats: int = 5,
    draws: int = 2000,
) -> dict[str, Any]:
    if outer_repeats < 1 or draws < 1:
        raise ValueError("Positive repeat and bootstrap counts required")
    with tempfile.TemporaryDirectory(prefix="native-dev-") as temporary:
        dev_labels = Path(temporary) / "development.csv"
        sizes = development_table(labels, HOLDOUT_SEED, dev_labels)
        payloads, subjects, y, _, development_digest = load_rows(dev_labels, images, plan)
    top = float(plan.rating_max)
    report: dict[str, Any] = {
        "policy": (
            "sealed seed-42 test subjects removed before ratings were parsed; nested grouped "
            "CV over development subjects only; no test metric computed or read"
        ),
        **sizes,
        "holdout_seed": HOLDOUT_SEED,
        "experiment_seed": seed,
        "development_collection_sha256": development_digest,
        "interval_scope": "descriptive subject resampling of fixed OOF errors; no refitting",
        "protocol_a_refit": "both selectors refit all outer-training subjects before scoring",
        "development_subjects": len(set(subjects)),
        "outer": f"repeated subject-grouped 5-fold x {outer_repeats}",
        "protocol_a": "single inner subject-hash validation split (~25%), alpha in {.01,1,100}",
        "protocol_b": f"inner grouped 5-fold x 3 CV, {len(ALPHA_GRID)}-point log alpha grid",
        "augmentation": "train folds only: brightness 0.85 + central 90% crop (original)",
        "encoders": {},
    }
    for encoder in encoders:
        started = time.perf_counter()
        extractor = create_extractor(encoder, encoder_root)
        x = features(payloads, extractor)
        views = np.stack(
            [
                features((perturb(p, kind) for p in payloads), extractor)
                for kind in ("lighting", "crop")
            ]
        )
        extraction = time.perf_counter() - started
        per_repeat: dict[str, list[Array]] = {"a": [], "b": [], "mean": []}
        alphas: dict[str, list[float]] = {"a": [], "b": []}
        fit_seconds = {"a": 0.0, "b": 0.0}
        for repeat in range(outer_repeats):
            predictions = {k: np.empty(len(y)) for k in per_repeat}
            for train, held in grouped_folds(subjects, 5, seed=seed + 1000 + repeat):
                inner = [subjects[i] for i in train]
                for name, protocol in (("a", protocol_a), ("b", protocol_b)):
                    tick = time.perf_counter()
                    head, alpha = protocol(x[train], views[:, train], y[train], inner, seed, top)
                    fit_seconds[name] += time.perf_counter() - tick
                    predictions[name][held] = head.predict(x[held])
                    alphas[name].append(alpha)
                predictions["mean"][held] = y[train].mean()
            for name in per_repeat:
                per_repeat[name].append(predictions[name])
        errors = {k: np.mean([np.abs(p - y) for p in v], axis=0) for k, v in per_repeat.items()}
        summary = {}
        for name, runs in per_repeat.items():
            scores = [metrics(p, y) for p in runs]
            summary[name] = {
                "mae": float(np.mean([s["mae"] for s in scores])),
                "rmse": float(np.mean([s["rmse"] for s in scores])),
                "spearman": None
                if name == "mean" or any(s["spearman"] is None for s in scores)
                else float(np.mean([s["spearman"] for s in scores])),
                "undefined_spearman_repeats": sum(s["spearman"] is None for s in scores),
                "mae_sd_across_repeats": float(np.std([s["mae"] for s in scores])),
            }
        report["encoders"][encoder] = {
            "outer_cv": summary,
            "selected_alpha_counts": {
                k: {str(a): v.count(a) for a in sorted(set(v))} for k, v in alphas.items()
            },
            "paired_b_minus_a_mae": paired_bootstrap(
                errors["a"], errors["b"], subjects, draws, 20261101
            ),
            "paired_b_minus_mean_baseline_mae": paired_bootstrap(
                errors["mean"], errors["b"], subjects, draws, 20261101
            ),
            "paired_a_minus_mean_baseline_mae": paired_bootstrap(
                errors["mean"], errors["a"], subjects, draws, 20261101
            ),
            "repeat_averaged_spearman_b": spearman(np.mean(per_repeat["b"], axis=0), y),
            "seconds": {
                "feature_extraction": extraction,
                "protocol_a_fitting": fit_seconds["a"],
                "protocol_b_fitting": fit_seconds["b"],
            },
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("labels", "images", "plan", "encoder-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--encoder", action="append", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--outer-repeats", type=int, default=5)
    args = parser.parse_args()
    try:
        plan = Collection.model_validate_json(args.plan.read_bytes())
        if plan.synthetic:
            raise ValueError("Development study requires genuine human labels")
        result = study(
            args.labels,
            args.images,
            plan,
            args.encoder_root,
            args.encoder,
            seed=args.seed,
            outer_repeats=args.outer_repeats,
        )
    except (OSError, ValueError) as exc:
        print(f"Development study refused: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
