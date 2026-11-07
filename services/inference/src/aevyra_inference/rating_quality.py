"""Rater-adjusted labels and inter-rater reliability for incomplete rating designs.

Studies assign each portrait to a different random subset of raters. On a subjective
1–7 scale, raters differ systematically: some are lenient, some severe. With a plain
mean, a portrait's label partly depends on *which* raters happened to see it. This
module fits the additive model

    score[image, rater] = mu + image_effect[image] + rater_offset[rater] + noise

using alternating least squares. Rater offsets are shrunk toward zero with a penalty
lambda = noise_var / rater_var, estimated by the method of moments, so raters with few
ratings move labels less. Image effects are not shrunk: the label keeps its own scale
rather than being pulled toward the average. If raters show no systematic offset
(rater_var estimated at 0), the adjusted label equals the plain mean.

Reliability uses repeated split halves with a bootstrap over images, converted to a
single-rater reliability and a Spearman-Brown projection. These figures describe how
consistently *these* raters agree. They are not model accuracy and not validity.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

Rating = tuple[str, str, float]  # (image, rater, score)


@dataclass(frozen=True)
class RaterModel:
    images: list[str]
    raters: list[str]
    mean: float
    image_effect: np.ndarray
    rater_offset: np.ndarray
    counts: np.ndarray
    raw_mean: np.ndarray
    noise_var: float
    rater_var: float
    shrinkage: float | None  # None: no detectable rater variance, offsets are zero
    iterations: int

    def adjusted(self, low: float = 1.0, high: float = 7.0) -> dict[str, float]:
        values = np.clip(self.mean + self.image_effect, low, high)
        return {image: float(v) for image, v in zip(self.images, values, strict=True)}


def _index(
    ratings: Sequence[Rating],
) -> tuple[list[str], list[str], np.ndarray, np.ndarray, np.ndarray]:
    if not ratings:
        raise ValueError("No ratings")
    images = sorted({r[0] for r in ratings})
    raters = sorted({r[1] for r in ratings})
    i_pos = {k: n for n, k in enumerate(images)}
    r_pos = {k: n for n, k in enumerate(raters)}
    ii = np.fromiter((i_pos[r[0]] for r in ratings), dtype=np.int64, count=len(ratings))
    rr = np.fromiter((r_pos[r[1]] for r in ratings), dtype=np.int64, count=len(ratings))
    y = np.fromiter((float(r[2]) for r in ratings), dtype=np.float64, count=len(ratings))
    if not np.isfinite(y).all():
        raise ValueError("Non-finite rating")
    pairs = set(zip(ii.tolist(), rr.tolist(), strict=True))
    if len(pairs) != len(ratings):
        raise ValueError("Each rater may contribute one primary rating per image")
    return images, raters, ii, rr, y


def _als(
    ii: np.ndarray,
    rr: np.ndarray,
    y: np.ndarray,
    n_i: int,
    n_r: int,
    penalty: float,
    *,
    tol: float = 1e-10,
) -> tuple[float, np.ndarray, np.ndarray, int]:
    mu = float(y.mean())
    a, b = np.zeros(n_i), np.zeros(n_r)
    cnt_i = np.bincount(ii, minlength=n_i).astype(float)
    cnt_r = np.bincount(rr, minlength=n_r).astype(float)
    for step in range(1, 1001):
        a_new = np.bincount(ii, weights=y - mu - b[rr], minlength=n_i) / cnt_i
        b_new = np.bincount(rr, weights=y - mu - a_new[ii], minlength=n_r) / (cnt_r + penalty)
        # Identify the grand mean: the average rating-weighted rater offset is zero.
        shift = float(np.average(b_new, weights=cnt_r))
        b_new -= shift
        a_new += shift
        change = max(np.abs(a_new - a).max(), np.abs(b_new - b).max())
        a, b = a_new, b_new
        if change < tol:
            return mu, a, b, step
    return mu, a, b, 1000


def fit_rater_model(ratings: Sequence[Rating]) -> RaterModel:
    images, raters, ii, rr, y = _index(ratings)
    n_i, n_r = len(images), len(raters)
    counts = np.bincount(ii, minlength=n_i)
    raw = np.bincount(ii, weights=y, minlength=n_i) / counts
    # Unpenalized fit for moment estimates (a tiny ridge keeps disconnected designs finite).
    mu, a, b, _ = _als(ii, rr, y, n_i, n_r, 1e-9)
    residual = y - mu - a[ii] - b[rr]
    dof = len(y) - n_i - n_r + 1
    noise_var = float(residual @ residual / dof) if dof > 0 else float("nan")
    cnt_r = np.bincount(rr, minlength=n_r).astype(float)
    rater_var = 0.0
    if dof > 0 and n_r > 1:
        # Observed offsets = true offsets + estimation error (about noise_var / n_r).
        rater_var = max(0.0, float(np.var(b, ddof=1) - np.mean(noise_var / cnt_r)))
    if not np.isfinite(noise_var) or rater_var <= 0.0:
        return RaterModel(
            images,
            raters,
            float(y.mean()),
            raw - float(y.mean()),
            np.zeros(n_r),
            counts,
            raw,
            noise_var,
            0.0,
            None,
            0,
        )
    penalty = noise_var / rater_var
    mu, a, b, steps = _als(ii, rr, y, n_i, n_r, penalty)
    return RaterModel(images, raters, mu, a, b, counts, raw, noise_var, rater_var, penalty, steps)


def _half_correlation(
    groups: list[np.ndarray], rng: np.random.Generator
) -> tuple[float, float] | None:
    first, second, sizes = [], [], []
    for scores in groups:
        order = rng.permutation(len(scores))
        half = len(scores) // 2
        first.append(scores[order[:half]].mean())
        second.append(scores[order[half : 2 * half]].mean())
        sizes.append(half)
    x, z = np.asarray(first), np.asarray(second)
    if x.std() == 0 or z.std() == 0:
        return None
    return float(np.corrcoef(x, z)[0, 1]), float(np.mean(sizes))


def single_rater(r_half: float, m: float) -> float:
    """Invert Spearman-Brown: correlation of m-rater means -> one-rater reliability."""
    return r_half / (m - (m - 1.0) * r_half)


def projected(rho: float, k: float) -> float:
    return k * rho / (1.0 + (k - 1.0) * rho)


def raters_needed(rho: float, target: float) -> int | None:
    if not 0 < rho < 1 or not 0 < target < 1:
        return None
    return int(np.ceil(target * (1 - rho) / (rho * (1 - target)) - 1e-9))


def reliability(
    ratings: Sequence[Rating], *, draws: int = 400, seed: int = 20261107, min_images: int = 10
) -> dict[str, Any]:
    """Split-half reliability with a bootstrap over images. Uses only images with >=2 ratings."""
    images, _, ii, _, y = _index(ratings)
    groups = [y[ii == n] for n in range(len(images))]
    usable = [g for g in groups if len(g) >= 2]
    counts = np.asarray([len(g) for g in groups])
    summary: dict[str, Any] = {
        "images": len(images),
        "images_with_two_or_more": len(usable),
        "ratings_per_image": {
            "min": int(counts.min()),
            "median": float(np.median(counts)),
            "max": int(counts.max()),
        },
        "method": "split-half with bootstrap over images; Spearman-Brown projection",
        "single_rater": None,
        "at_current_coverage": None,
        "interval_95": None,
        "raters_needed": {"0.7": None, "0.8": None, "0.9": None},
    }
    if len(usable) < min_images:
        summary["status"] = "insufficient_data"
        return summary
    rng = np.random.default_rng(seed)
    singles = []
    for _ in range(draws):
        sample = [usable[k] for k in rng.integers(0, len(usable), len(usable))]
        result = _half_correlation(sample, rng)
        if result is None:
            continue
        r_half, m = result
        if r_half <= 0:
            singles.append(0.0)
            continue
        singles.append(min(single_rater(r_half, m), 0.999))
    if len(singles) < draws // 2:
        summary["status"] = "insufficient_variation"
        return summary
    values = np.asarray(singles)
    rho = float(np.median(values))
    k = float(np.median(counts[counts >= 2]))
    summary.update(
        status="estimated",
        single_rater=rho,
        at_current_coverage=projected(rho, k),
        interval_95=[
            projected(float(np.quantile(values, 0.025)), k),
            projected(float(np.quantile(values, 0.975)), k),
        ],
        raters_needed={str(t): raters_needed(rho, t) for t in (0.7, 0.8, 0.9)},
    )
    return summary
