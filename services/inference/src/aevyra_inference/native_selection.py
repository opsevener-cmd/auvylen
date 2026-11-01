"""Subject-grouped cross-validated ridge selection for native-scale heads.

The original protocol picks one of three penalties (.01, 1, 100) from a single
validation partition. With ~20 validation subjects that choice is high-variance, and
alpha=.01 with ~60 images and 1024 standardized features is effectively an interpolating
fit. This module selects the penalty by repeated subject-grouped K-fold cross-validation
over development subjects only, using one SVD per fold to evaluate a whole log-spaced
grid exactly. Sealed test subjects must never be passed in.
"""

import hashlib
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from aevyra_inference.native import Array, NativeHead

ALPHA_GRID: tuple[float, ...] = tuple(float(a) for a in np.logspace(-2, 5, 15))


def grouped_folds(
    subjects: list[str], k: int, *, seed: int, repeats: int = 1
) -> list[tuple[NDArray[np.int_], NDArray[np.int_]]]:
    """Deterministic subject-grouped folds: every image of a person stays in one fold."""
    unique = sorted(set(subjects))
    if k < 2 or len(unique) < k or repeats < 1:
        raise ValueError("Grouped folds need k>=2 and at least k independent subjects")
    position = np.asarray(subjects)
    folds = []
    for repeat in range(repeats):
        order = sorted(
            unique, key=lambda s: hashlib.sha256(f"{seed}:{repeat}:{s}".encode()).digest()
        )
        for fold in range(k):
            held = set(order[fold::k])
            mask = np.isin(position, list(held))
            folds.append((np.flatnonzero(~mask), np.flatnonzero(mask)))
    return folds


@dataclass(frozen=True)
class RidgePath:
    """Exact ridge solutions for many penalties from one thin SVD of standardized data."""

    mean: Array
    scale: Array
    intercept: float
    u_t_target: Array
    singular: Array
    v: Array

    @classmethod
    def fit(cls, x: Array, y: Array) -> "RidgePath":
        if x.ndim != 2 or y.shape != (len(x),) or len(x) < 2 or not np.isfinite(x).all():
            raise ValueError("Invalid ridge-path training data")
        if not np.isfinite(y).all() or np.ptp(y) == 0:
            raise ValueError("Finite varied training labels required")
        # Same training-only standardization and unpenalized intercept as native.fit_head.
        mean, scale = x.mean(0), np.maximum(x.std(0), 0.05)
        z = (x - mean) / scale
        intercept = float(y.mean())
        u, s, vt = np.linalg.svd(z, full_matrices=False)
        return cls(mean, scale, intercept, u.T @ (y - intercept), s, vt.T)

    def weights(self, alpha: float) -> Array:
        if not np.isfinite(alpha) or alpha <= 0:
            raise ValueError("Positive ridge penalty required")
        shrink = self.singular / (self.singular**2 + alpha)
        return np.asarray(self.v @ (shrink * self.u_t_target), dtype=np.float64)

    def head(self, alpha: float, rating_max: float) -> NativeHead:
        return NativeHead(self.mean, self.scale, self.weights(alpha), self.intercept, rating_max)


def cv_curve(
    x: Array,
    y: Array,
    subjects: list[str],
    *,
    rating_max: float,
    alphas: tuple[float, ...] = ALPHA_GRID,
    k: int = 5,
    repeats: int = 3,
    seed: int = 42,
    views: Array | None = None,
) -> dict[float, float]:
    """Mean held-fold MAE per penalty. Augmented views are used only for training folds."""
    if views is not None and (views.ndim != 3 or views.shape[1:] != x.shape):
        raise ValueError("Augmented views must align with development images")
    errors: dict[float, list[float]] = {alpha: [] for alpha in alphas}
    for train, held in grouped_folds(subjects, k, seed=seed, repeats=repeats):
        tx, ty = x[train], y[train]
        if views is not None:
            tx = np.concatenate([tx, *views[:, train]])
            ty = np.tile(ty, len(views) + 1)
        path = RidgePath.fit(tx, ty)
        for alpha in alphas:
            predicted = path.head(alpha, rating_max).predict(x[held])
            errors[alpha].append(float(np.abs(predicted - y[held]).mean()))
    return {alpha: float(np.mean(values)) for alpha, values in errors.items()}


def select_alpha(curve: dict[float, float]) -> float:
    """Lowest grouped-CV MAE; exact ties resolve to the stronger (larger) penalty."""
    return min(curve, key=lambda alpha: (round(curve[alpha], 12), -alpha))
