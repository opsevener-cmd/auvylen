"""Original Auvylen aesthetic rating-distribution model (Phase 6A).

A linear head maps a frozen visual feature vector to five rating probabilities, trained
with a cumulative (CDF) squared-error loss on real human vote distributions. The score
describes the training annotators' statistical preferences, never objective beauty.
This module is independent of personal preference models and the synthetic mock.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

RATING_BINS = 5
SEED = 42
MIN_IMAGES = 60
MIN_SUBJECTS = 15
LEVELS = np.arange(1, RATING_BINS + 1, dtype=np.float64)
CALIBRATION_LEVEL = 0.9

Array = NDArray[np.float64]


def softmax(z: Array) -> Array:
    z = np.asarray(z, dtype=np.float64)
    z = z - np.max(z, axis=1, keepdims=True)
    exp_z = np.exp(z)
    return np.asarray(exp_z / exp_z.sum(axis=1, keepdims=True), dtype=np.float64)


def normalize_votes(votes: NDArray[Any]) -> Array:
    votes = np.asarray(votes, dtype=np.float64)
    if votes.ndim != 2 or votes.shape[1] != RATING_BINS:
        raise ValueError("Expected five rating categories.")
    if not np.isfinite(votes).all() or np.any(votes < 0):
        raise ValueError("Invalid human rating counts.")
    totals = votes.sum(axis=1, keepdims=True)
    if np.any(totals <= 0):
        raise ValueError("Every image needs real ratings.")
    return np.asarray(votes / totals, dtype=np.float64)


def distribution_loss(predictions: Array, targets: Array) -> tuple[float, Array]:
    """Mean over images of (1/5) sum_k (CDF_p(k) - CDF_q(k))^2, and dL/dz through softmax."""
    difference = np.cumsum(predictions - targets, axis=1)
    loss = float(np.mean(difference**2))
    # dL/dp_i = (2/N) sum_{k>=i} d_k: a reversed cumulative sum of the CDF differences.
    gradient_p = (2.0 / difference.size) * np.flip(
        np.cumsum(np.flip(difference, axis=1), axis=1), axis=1
    )
    gradient_z = predictions * (
        gradient_p - np.sum(gradient_p * predictions, axis=1, keepdims=True)
    )
    return loss, np.asarray(gradient_z, dtype=np.float64)


def objective(
    x: Array, targets: Array, weights: Array, bias: Array, weight_decay: float
) -> tuple[float, Array, Array]:
    """Training objective L + (weight_decay / 2) ||W||^2 with exact analytic gradients."""
    loss, grad_z = distribution_loss(softmax(x @ weights + bias), targets)
    penalty = 0.5 * weight_decay * float(np.sum(weights**2))
    return loss + penalty, x.T @ grad_z + weight_decay * weights, grad_z.sum(axis=0)


def expected_score(probabilities: Array) -> Array:
    return np.asarray(probabilities @ LEVELS, dtype=np.float64)


def rating_spread(probabilities: Array) -> Array:
    """Standard deviation of the rating distribution on the 1-5 scale (annotator disagreement)."""
    mean = expected_score(probabilities)
    variance = probabilities @ (LEVELS**2) - mean**2
    return np.asarray(np.sqrt(np.maximum(variance, 0.0)), dtype=np.float64)


def display_score(score_5: Array) -> Array:
    return np.asarray(1.0 + 2.25 * (score_5 - 1.0), dtype=np.float64)


def split_by_subject(
    subject_ids: list[str], seed: int = SEED
) -> tuple[NDArray[np.int_], NDArray[np.int_], NDArray[np.int_]]:
    if any(not s or not s.strip() for s in subject_ids):
        raise ValueError("Missing subject identifiers.")
    subjects = sorted(
        set(subject_ids), key=lambda s: hashlib.sha256(f"{seed}:{s}".encode()).digest()
    )
    if len(subjects) < MIN_SUBJECTS:
        raise ValueError("At least 15 independent subjects required.")
    n = max(1, round(len(subjects) * 0.2))
    test_subjects = set(subjects[:n])
    val_subjects = set(subjects[n : 2 * n])
    train, val, test = [], [], []
    for i, subject in enumerate(subject_ids):
        if subject in test_subjects:
            test.append(i)
        elif subject in val_subjects:
            val.append(i)
        else:
            train.append(i)
    return (
        np.asarray(train, dtype=int),
        np.asarray(val, dtype=int),
        np.asarray(test, dtype=int),
    )


def _ranks(values: Array) -> Array:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    ordered = values[order]
    start = 0
    while start < len(values):
        end = start
        while end + 1 < len(values) and ordered[end + 1] == ordered[start]:
            end += 1
        ranks[order[start : end + 1]] = (start + end) / 2 + 1  # Average rank for ties.
        start = end + 1
    return ranks


def pearson(a: Array, b: Array) -> float | None:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None  # Undefined, never reported as zero correlation.
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a: Array, b: Array) -> float | None:
    return pearson(_ranks(np.asarray(a, dtype=np.float64)), _ranks(np.asarray(b, dtype=np.float64)))


def conformal_half_width(absolute_errors: Array, level: float = CALIBRATION_LEVEL) -> float | None:
    """Split-conformal radius with the finite-sample (n + 1) correction; None if too few."""
    n = len(absolute_errors)
    rank = math.ceil((n + 1) * level)
    if n == 0 or rank > n:
        return None
    return float(np.sort(absolute_errors)[rank - 1])


@dataclass(frozen=True)
class ScoringHead:
    mean: Array
    scale: Array
    weights: Array
    bias: Array

    def predict_distribution(self, features: NDArray[Any]) -> Array:
        x = np.asarray(features, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.mean.size:
            raise ValueError("Invalid feature dimensions.")
        if not np.isfinite(x).all():
            raise ValueError("Non-finite features.")
        normalized = (x - self.mean) / self.scale
        return softmax(normalized @ self.weights + self.bias)

    def predict(self, features: NDArray[Any]) -> dict[str, list[Any]]:
        probabilities = self.predict_distribution(features)
        score_5 = expected_score(probabilities)
        return {
            "score": display_score(score_5).tolist(),
            "rating_distribution": probabilities.tolist(),
        }


def _regression_metrics(predicted: Array, target: Array) -> dict[str, float | None]:
    return {
        "mae": float(np.mean(np.abs(predicted - target))),
        "rmse": float(np.sqrt(np.mean((predicted - target) ** 2))),
        "spearman": spearman(predicted, target),
        "pearson": pearson(predicted, target),
    }


def fit_scoring_head(
    features: NDArray[Any],
    human_votes: NDArray[Any],
    subject_ids: list[str],
    *,
    learning_rate: float = 0.003,
    weight_decay: float = 0.0005,
    epochs: int = 250,
    patience: int = 30,
    seed: int = SEED,
    check: Callable[[], None] | None = None,
) -> tuple[ScoringHead, dict[str, Any]]:
    X = np.asarray(features, dtype=np.float64)
    Y = normalize_votes(human_votes)
    if X.ndim != 2 or X.shape[1] < 1:
        raise ValueError("Invalid features.")
    if not np.isfinite(X).all():
        raise ValueError("Non-finite features.")
    if len(X) != len(Y) or len(X) != len(subject_ids):
        raise ValueError("Dataset dimensions do not match.")
    if len(X) < MIN_IMAGES:
        raise ValueError("At least 60 labeled images required.")
    if learning_rate <= 0 or weight_decay < 0 or not math.isfinite(learning_rate + weight_decay):
        raise ValueError("Invalid optimization parameters.")
    if epochs < 1 or patience < 1:
        raise ValueError("Invalid training configuration.")

    train_idx, val_idx, test_idx = split_by_subject(subject_ids, seed)
    # Reserve half of the validation subjects for calibration, never epoch selection.
    validation_subjects = sorted({subject_ids[i] for i in val_idx})
    calibration_subjects = set(validation_subjects[::2])
    cal_idx = np.asarray([i for i in val_idx if subject_ids[i] in calibration_subjects], dtype=int)
    val_idx = np.asarray(
        [i for i in val_idx if subject_ids[i] not in calibration_subjects], dtype=int
    )
    Y_train, Y_val, Y_test = Y[train_idx], Y[val_idx], Y[test_idx]
    if np.ptp(expected_score(Y_train)) == 0:
        raise ValueError("Training ratings need variation.")

    # Normalization statistics come from training subjects only; validation/test never leak.
    mean = X[train_idx].mean(axis=0)
    scale = np.maximum(X[train_idx].std(axis=0), 0.05)
    X_train = (X[train_idx] - mean) / scale
    X_val = (X[val_idx] - mean) / scale

    rng = np.random.default_rng(seed)
    W = rng.normal(0.0, 0.005, size=(X.shape[1], RATING_BINS))
    b = np.zeros(RATING_BINS, dtype=np.float64)
    mW, vW = np.zeros_like(W), np.zeros_like(W)
    mb, vb = np.zeros_like(b), np.zeros_like(b)
    beta1, beta2, epsilon = 0.9, 0.999, 1e-8

    best_loss = float("inf")
    best_W, best_b = W.copy(), b.copy()
    best_epoch = 0
    epochs_run = 0
    for epoch in range(1, epochs + 1):
        epochs_run = epoch
        _, grad_W, grad_b = objective(X_train, Y_train, W, b, weight_decay)
        mW = beta1 * mW + (1 - beta1) * grad_W
        vW = beta2 * vW + (1 - beta2) * grad_W**2
        mb = beta1 * mb + (1 - beta1) * grad_b
        vb = beta2 * vb + (1 - beta2) * grad_b**2
        W -= (
            learning_rate * (mW / (1 - beta1**epoch)) / (np.sqrt(vW / (1 - beta2**epoch)) + epsilon)
        )
        b -= (
            learning_rate * (mb / (1 - beta1**epoch)) / (np.sqrt(vb / (1 - beta2**epoch)) + epsilon)
        )
        if not (np.isfinite(W).all() and np.isfinite(b).all()):
            raise ValueError("Training diverged.")
        val_loss, _ = distribution_loss(softmax(X_val @ W + b), Y_val)
        if val_loss < best_loss - 1e-8:
            best_loss, best_W, best_b, best_epoch = val_loss, W.copy(), b.copy(), epoch
        if epoch - best_epoch >= patience:
            break
        if check is not None and epoch % 10 == 0:
            check()

    head = ScoringHead(mean=mean, scale=scale, weights=best_W, bias=best_b)

    # Each independent person contributes one maximum residual. Repeated photographs
    # must not be treated as independent calibration observations.
    train_scores = expected_score(Y_train)
    cal_pred = head.predict_distribution(X[cal_idx])
    cal_errors = np.abs(
        display_score(expected_score(cal_pred)) - display_score(expected_score(Y[cal_idx]))
    )
    subject_errors = np.asarray(
        [
            max(
                error
                for index, error in zip(cal_idx, cal_errors, strict=True)
                if subject_ids[index] == subject
            )
            for subject in sorted(calibration_subjects)
        ]
    )
    half_width = conformal_half_width(subject_errors)

    test_pred = head.predict_distribution(X[test_idx])
    predicted_scores = expected_score(test_pred)
    target_scores = expected_score(Y_test)
    test_loss, _ = distribution_loss(test_pred, Y_test)
    mean_baseline = float(train_scores.mean())
    mean_distribution = np.broadcast_to(Y_train.mean(axis=0), Y_test.shape)
    baseline_loss, _ = distribution_loss(np.asarray(mean_distribution), Y_test)
    model = _regression_metrics(predicted_scores, target_scores)
    errors_10 = np.abs(display_score(predicted_scores) - display_score(target_scores))

    metrics: dict[str, Any] = {
        "labeled_images": len(X),
        "training_images": len(train_idx),
        "validation_images": len(val_idx),
        "calibration_images": len(cal_idx),
        "calibration_subjects": len(calibration_subjects),
        "test_images": len(test_idx),
        "training_subjects": len({subject_ids[i] for i in train_idx}),
        "validation_subjects": len({subject_ids[i] for i in val_idx}),
        "test_subjects": len({subject_ids[i] for i in test_idx}),
        "best_epoch": best_epoch,
        "epochs_run": epochs_run,
        "validation_distribution_loss": best_loss,
        "test_distribution_loss": test_loss,
        "test_mae": model["mae"],
        "test_rmse": model["rmse"],
        "test_spearman": model["spearman"],
        "test_pearson": model["pearson"],
        "test_mae_display": float(np.mean(errors_10)),
        "mean_baseline_mae": float(np.mean(np.abs(mean_baseline - target_scores))),
        "mean_baseline_rmse": float(np.sqrt(np.mean((mean_baseline - target_scores) ** 2))),
        "mean_distribution_baseline_loss": baseline_loss,
        # Does the predicted spread track real annotator disagreement on held-out subjects?
        "test_spread_mae": float(np.mean(np.abs(rating_spread(test_pred) - rating_spread(Y_test)))),
        "mean_target_spread": float(np.mean(rating_spread(Y_test))),
        "calibration": {
            "method": (
                "split-conformal subject-max absolute error on independent "
                "calibration subjects, display scale"
            ),
            "level": CALIBRATION_LEVEL,
            "validation_n": len(subject_errors),
            "half_width_display": half_width,
            "test_coverage": None
            if half_width is None
            else float(np.mean(errors_10 <= half_width)),
        },
        "split_seed": seed,
        "split": {
            "training": train_idx.tolist(),
            "validation": val_idx.tolist(),
            "calibration": cal_idx.tolist(),
            "test": test_idx.tolist(),
        },
    }
    return head, metrics


def analyze(head: ScoringHead, features: NDArray[Any]) -> dict[str, Any]:
    """One image: distribution, S5, S10 and annotator-disagreement spread (not uncertainty)."""
    probabilities = head.predict_distribution(np.asarray([features], dtype=np.float64))
    score_5 = expected_score(probabilities)
    score_10 = display_score(score_5)
    spread = rating_spread(probabilities)
    return {
        "rating_distribution": [float(v) for v in probabilities[0]],
        "expected_rating_5": float(score_5[0]),
        "score_10": float(min(10.0, max(1.0, score_10[0]))),
        "rating_spread_5": float(spread[0]),
        "rating_spread_10": float(2.25 * spread[0]),
    }
