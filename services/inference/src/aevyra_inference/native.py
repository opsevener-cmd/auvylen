"""Auvylen native-scale ridge head: frozen visual encoder, independently fitted labels.

Population research model, independent of per-account preference models and Phase 6's
vote-distribution head. No pretrained attractiveness weights or distribution labels.
"""

from dataclasses import dataclass
from typing import Any, Literal

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
    rating_max: float = 5.0

    def predict(self, features: NDArray[Any]) -> Array:
        x = np.asarray(features, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.weights.size or not np.isfinite(x).all():
            raise ValueError("Invalid native-model features")
        # Declared-native-scale bounds are identical during selection, evaluation and runtime.
        return np.asarray(
            np.clip(
                (x - self.mean) / self.scale @ self.weights + self.intercept, 1.0, self.rating_max
            ),
            dtype=np.float64,
        )


def fit_head(x: Array, y: Array, alpha: float, rating_max: float = 5.0) -> NativeHead:
    if rating_max not in (5, 7):
        raise ValueError("Unsupported native scale")
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
    return NativeHead(mean, scale, np.asarray(weights, dtype=np.float64), intercept, rating_max)


def effective_dof(x: Array, alpha: float) -> float:
    """Ridge effective degrees of freedom on training-standardized features.

    Values close to the number of distinct training images indicate a nearly
    interpolating fit (e.g. alpha=.01 with 1024 features and ~60 portraits).
    """
    z = (x - x.mean(0)) / np.maximum(x.std(0), 0.05)
    singular = np.linalg.svd(z, compute_uv=False)
    return float(np.sum(singular**2 / (singular**2 + alpha)))


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
    rating_max: int = 5,
    train_views: dict[str, Array] | None = None,
    selection: Literal["validation", "grouped-cv"] = "validation",
    development_views: dict[str, Array] | None = None,
) -> tuple[str, NativeHead, dict[str, Any]]:
    """Fix one encoder/penalty without test labels, then evaluate the sealed test once.

    ``validation`` reproduces the original pilot rule (three penalties, one validation
    split). ``grouped-cv`` selects from a log grid by repeated subject-grouped 5-fold CV
    over train+validation subjects and refits on all of them; ``development_views`` then
    holds augmented views aligned with ``sorted(train + validation)`` indices.
    """
    if (
        len(labels) < 60
        or not np.isfinite(labels).all()
        or np.any((labels < 1) | (labels > rating_max))
    ):
        raise ValueError("At least 60 finite native-scale ratings required")
    if rating_max not in (5, 7):
        raise ValueError("Unsupported native rating scale")
    if len(subjects) != len(labels) or not features:
        raise ValueError("Dataset dimensions mismatch")
    train, val, test = split_by_subject(subjects, seed)
    if min(len(train), len(val), len(test)) < 3:
        raise ValueError("Each partition needs at least three images")
    if selection == "grouped-cv":
        return _select_grouped_cv(
            features, labels, subjects, seed, rating_max, train, val, test, development_views
        )
    if selection != "validation":
        raise ValueError("Unknown selection protocol")
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
            head = fit_head(tx, ty, alpha, rating_max)
            score = metrics(head.predict(x[val]), labels[val])
            candidates.append((score["mae"], name, alpha, head, score))
    # Test labels are not read until a single encoder/penalty winner is fixed.
    _, winner, alpha, head, validation = min(candidates, key=lambda c: c[:3])
    fitted = features[winner][train]
    if train_views is not None:
        fitted = np.concatenate([fitted, *train_views[winner]])
    ytest = labels[test]
    report: dict[str, Any] = {
        "selection_protocol": "validation-3",
        "effective_degrees_of_freedom": effective_dof(fitted, alpha),
        "distinct_training_images": len(train),
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


def _select_grouped_cv(
    features: dict[str, Array],
    labels: Array,
    subjects: list[str],
    seed: int,
    rating_max: int,
    train: NDArray[np.int_],
    val: NDArray[np.int_],
    test: NDArray[np.int_],
    development_views: dict[str, Array] | None,
) -> tuple[str, NativeHead, dict[str, Any]]:
    # Imported lazily: native_selection depends on this module's NativeHead.
    from aevyra_inference.native_selection import ALPHA_GRID, cv_curve, select_alpha

    development = np.sort(np.concatenate([train, val]))
    dev_subjects = [subjects[i] for i in development]
    y = labels[development]
    curves, choices = {}, []
    for name, x in sorted(features.items()):
        if x.ndim != 2 or len(x) != len(labels) or not np.isfinite(x).all():
            raise ValueError("Invalid encoder features")
        views = None if development_views is None else development_views[name]
        if views is not None and (views.ndim != 3 or views.shape[1:] != x[development].shape):
            raise ValueError("Augmented views must align with development indices")
        curve = cv_curve(
            x[development], y, dev_subjects, rating_max=rating_max, seed=seed, views=views
        )
        alpha = select_alpha(curve)
        curves[name] = curve
        choices.append((curve[alpha], name, alpha))
    # Encoder and penalty are fixed from development CV only; test labels unread so far.
    cv_mae, winner, alpha = min(choices)
    heads, fitted_rows = {}, {}
    for _, name, a in choices:
        views = None if development_views is None else development_views[name]
        tx = features[name][development]
        ty = y
        if views is not None:
            tx = np.concatenate([tx, *views])
            ty = np.tile(y, len(views) + 1)
        heads[name] = fit_head(tx, ty, a, rating_max)
        fitted_rows[name] = tx
    head = heads[winner]
    ytest = labels[test]
    report: dict[str, Any] = {
        "selection_protocol": "grouped-cv",
        "selected_encoder": winner,
        "selected_alpha": alpha,
        "effective_degrees_of_freedom": effective_dof(fitted_rows[winner], alpha),
        "distinct_training_images": len(development),
        "seed": seed,
        "validation": {"n": len(development), "mae": cv_mae, "rmse": None, "spearman": None},
        "selection": [
            {"encoder": name, "alpha": a, "validation": {"mae": m, "rmse": None, "spearman": None}}
            for name, curve in curves.items()
            for a, m in curve.items()
        ],
        "selection_grid": list(ALPHA_GRID),
        "test": metrics(head.predict(features[winner][test]), ytest),
        "mean_baseline": metrics(np.full(len(test), y.mean()), ytest),
        "median_baseline": metrics(np.full(len(test), np.median(y)), ytest),
        "partition_sizes": {
            "train": len(train),
            "validation": len(val),
            "test": len(test),
            "fitted_development": len(development),
        },
        "subject_counts": {
            k: len({subjects[i] for i in indices})
            for k, indices in [("train", train), ("validation", val), ("test", test)]
        },
        "encoder_comparison": {
            name: metrics(heads[name].predict(features[name][test]), ytest) for name in heads
        },
    }
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
