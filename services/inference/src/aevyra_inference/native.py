"""Auvylen native-scale ridge head: frozen visual encoder, independently fitted labels.

Population research model, independent of per-account preference models and Phase 6's
vote-distribution head. No pretrained attractiveness weights or distribution labels.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from aevyra_inference.aesthetic import spearman, split_by_subject

Array = NDArray[np.float64]
ALPHAS = (0.01, 1.0, 100.0)


@dataclass(frozen=True)
class NativeHead:
    mean: Array
    scale: Array
    weights: Array
    intercept: float

    def predict(self, features: NDArray[Any]) -> Array:
        x = np.asarray(features, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.weights.size or not np.isfinite(x).all():
            raise ValueError("Invalid native-model features")
        # Bounded native 1–5 estimator, applied identically in selection/evaluation/runtime.
        return np.asarray(
            np.clip((x - self.mean) / self.scale @ self.weights + self.intercept, 1.0, 5.0),
            dtype=np.float64,
        )


def fit_head(x: Array, y: Array, alpha: float) -> NativeHead:
    if not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("Positive ridge penalty required")
    if x.ndim != 2 or y.shape != (len(x),) or len(x) < 2:
        raise ValueError("Invalid training dimensions")
    if not np.isfinite(x).all() or not np.isfinite(y).all() or np.ptp(y) == 0:
        raise ValueError("Finite varied training labels required")
    mean, scale = x.mean(0), np.maximum(x.std(0), 0.05)
    z, intercept = (x - mean) / scale, float(y.mean())
    target = y - intercept
    # Solve smaller system: CPU/RAM bounded for 1024 features and small initial cohorts.
    if z.shape[1] <= len(z):
        weights = np.linalg.solve(z.T @ z + alpha * np.eye(z.shape[1]), z.T @ target)
    else:
        weights = z.T @ np.linalg.solve(z @ z.T + alpha * np.eye(len(z)), target)
    return NativeHead(mean, scale, np.asarray(weights, dtype=np.float64), intercept)


def metrics(predicted: Array, target: Array) -> dict[str, Any]:
    errors = predicted - target
    return {
        "n": len(target),
        "mae": float(np.abs(errors).mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "spearman": spearman(predicted, target),
    }


def select_model(
    features: dict[str, Array],
    labels: Array,
    subjects: list[str],
    *,
    seed: int = 42,
    train_views: dict[str, Array] | None = None,
) -> tuple[str, NativeHead, dict[str, Any]]:
    if len(labels) < 60 or not np.isfinite(labels).all() or np.any((labels < 1) | (labels > 5)):
        raise ValueError("At least 60 finite native-scale ratings required")
    if len(subjects) != len(labels) or not features:
        raise ValueError("Dataset dimensions mismatch")
    train, val, test = split_by_subject(subjects, seed)
    if min(len(train), len(val), len(test)) < 3:
        raise ValueError("Each partition needs at least three images")
    candidates = []
    for name, x in sorted(features.items()):
        if x.ndim != 2 or len(x) != len(labels) or not np.isfinite(x).all():
            raise ValueError("Invalid encoder features")
        tx, ty = x[train], labels[train]
        if train_views is not None:
            views = train_views[name]
            if views.ndim != 3 or views.shape[1:] != tx.shape or not np.isfinite(views).all():
                raise ValueError("Augmented views must contain training indices only")
            tx = np.concatenate([tx, *views])
            ty = np.tile(ty, len(views) + 1)
        for alpha in ALPHAS:
            head = fit_head(tx, ty, alpha)
            score = metrics(head.predict(x[val]), labels[val])
            candidates.append((score["mae"], name, alpha, head, score))
    # Test labels are not read until a single encoder/penalty winner is fixed.
    _, winner, alpha, head, validation = min(candidates, key=lambda c: c[:3])
    ytest = labels[test]
    report: dict[str, Any] = {
        "seed": seed,
        "selected_encoder": winner,
        "selected_alpha": alpha,
        "validation": validation,
        "selection": [
            {"encoder": name, "alpha": a, "validation": score}
            for _, name, a, _, score in candidates
        ],
        "test": metrics(head.predict(features[winner][test]), ytest),
        "mean_baseline": metrics(np.full(len(test), labels[train].mean()), ytest),
        "median_baseline": metrics(np.full(len(test), np.median(labels[train])), ytest),
        "partition_sizes": {"train": len(train), "validation": len(val), "test": len(test)},
        "subject_counts": {
            k: len({subjects[i] for i in indices})
            for k, indices in [("train", train), ("validation", val), ("test", test)]
        },
    }
    report["encoder_comparison"] = {}
    for name in sorted(features):
        best = min((c for c in candidates if c[1] == name), key=lambda c: c[:3])
        report["encoder_comparison"][name] = metrics(best[3].predict(features[name][test]), ytest)
    report["subject_macro_mae"] = float(
        np.mean(
            [
                np.abs(
                    head.predict(features[winner][test])[np.array([subjects[i] == s for i in test])]
                    - ytest[np.array([subjects[i] == s for i in test])]
                ).mean()
                for s in sorted({subjects[i] for i in test})
            ]
        )
    )
    return winner, head, report
