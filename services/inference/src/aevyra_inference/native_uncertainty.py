"""Cluster-bootstrap uncertainty for fixed held-out predictions, never model selection."""

from typing import Any

import numpy as np

from aevyra_inference.native import Array, metrics


def uncertainty(
    predicted: Array,
    target: Array,
    subjects: list[str],
    baseline: Array,
    *,
    draws: int = 2000,
    seed: int = 20261101,
) -> dict[str, Any]:
    if not all(np.isfinite(x).all() for x in (predicted, target, baseline)) or any(
        not s.strip() for s in subjects
    ):
        raise ValueError("Finite predictions and stable subject identifiers required")
    if (
        predicted.shape != target.shape
        or baseline.shape != target.shape
        or len(subjects) != len(target)
    ):
        raise ValueError("Bootstrap dimensions mismatch")
    if draws < 100 or len(set(subjects)) < 5:
        raise ValueError("At least five held-out subjects and 100 bootstrap draws required")
    rng = np.random.default_rng(seed)
    unique = sorted(set(subjects))
    groups = [np.flatnonzero(np.asarray(subjects) == subject) for subject in unique]
    values: dict[str, list[float]] = {
        k: [] for k in ("mae", "rmse", "spearman", "paired_mean_baseline_delta_mae")
    }
    for _ in range(draws):
        indices = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        score = metrics(predicted[indices], target[indices])
        score["paired_mean_baseline_delta_mae"] = float(
            np.mean(
                np.abs(predicted[indices] - target[indices])
                - np.abs(baseline[indices] - target[indices])
            )
        )
        for key in values:
            if score[key] is not None and np.isfinite(score[key]):
                values[key].append(float(score[key]))
    return {
        "method": (
            "held-out subject cluster percentile bootstrap; "
            "conditional on fixed trained model and rater pool"
        ),
        "level": 0.95,
        "draws": draws,
        "seed": seed,
        "subjects": len(unique),
        "intervals": {
            key: {
                "low": float(np.quantile(v, 0.025)),
                "high": float(np.quantile(v, 0.975)),
                "valid_draws": len(v),
            }
            if v
            else None
            for key, v in values.items()
        },
    }
