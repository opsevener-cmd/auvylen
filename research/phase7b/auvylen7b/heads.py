"""Heads on frozen features: the pilot's ridge rule and a rating-distribution head.

The distribution head predicts the share of raters choosing each native rating 1..7
(real per-rater histograms; never derived from means) with soft-label multinomial
logistic regression. Its score is the expected rating; its spread estimates how much
raters disagree. Standardization uses training rows only. Penalties are chosen by
subject-grouped inner CV over the training subjects only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LEVELS = np.arange(1, 8, dtype=np.float64)
PENALTIES = (1e-3, 1e-2, 1e-1, 1.0, 10.0)


@dataclass(frozen=True)
class DistributionHead:
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray  # (d, 7)
    bias: np.ndarray  # (7,)

    def distribution(self, x: np.ndarray) -> np.ndarray:
        z = (x - self.mean) / self.scale
        logits = z @ self.weights + self.bias
        logits -= logits.max(axis=1, keepdims=True)
        p = np.exp(logits)
        return p / p.sum(axis=1, keepdims=True)

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.distribution(x) @ LEVELS

    def spread(self, x: np.ndarray) -> np.ndarray:
        p = self.distribution(x)
        mu = p @ LEVELS
        return np.sqrt(np.clip(p @ LEVELS**2 - mu**2, 0, None))


def fit_distribution(
    x: np.ndarray, targets: np.ndarray, penalty: float, *, steps: int = 400
) -> DistributionHead:
    """Mean cross-entropy against soft targets + penalty/2 * ||W||^2; Adam, deterministic."""
    if x.ndim != 2 or targets.shape != (len(x), 7) or not np.allclose(targets.sum(1), 1):
        raise ValueError("Invalid distribution training data")
    mean, scale = x.mean(0), np.maximum(x.std(0), 0.05)
    z = (x - mean) / scale
    n, d = z.shape
    w, b = np.zeros((d, 7)), np.log(np.clip(targets.mean(0), 1e-6, None))
    m = [np.zeros_like(w), np.zeros_like(b)]
    v = [np.zeros_like(w), np.zeros_like(b)]
    rate, beta1, beta2 = 0.05, 0.9, 0.999
    for t in range(1, steps + 1):
        logits = z @ w + b
        logits -= logits.max(axis=1, keepdims=True)
        p = np.exp(logits)
        p /= p.sum(axis=1, keepdims=True)
        error = (p - targets) / n
        grads = [z.T @ error + penalty * w, error.sum(0)]
        for k, (param, grad) in enumerate(zip((w, b), grads, strict=True)):
            m[k] = beta1 * m[k] + (1 - beta1) * grad
            v[k] = beta2 * v[k] + (1 - beta2) * grad**2
            step = rate * (m[k] / (1 - beta1**t)) / (np.sqrt(v[k] / (1 - beta2**t)) + 1e-8)
            param -= step
    return DistributionHead(mean, scale, w, b)


def cross_entropy(p: np.ndarray, targets: np.ndarray) -> float:
    return float(-(targets * np.log(np.clip(p, 1e-9, 1))).sum(1).mean())


def earth_movers(p: np.ndarray, targets: np.ndarray) -> float:
    """1-D Wasserstein distance between ordinal distributions, in native rating points."""
    return float(np.abs(np.cumsum(p - targets, axis=1)).sum(1).mean())
