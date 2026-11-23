"""Rater-adjusted labels and inter-rater reliability for incomplete rating designs.

Studies assign each portrait to a different random subset of raters. On a subjective
1–7 scale, raters differ systematically: some are lenient, some severe. With a plain
mean, a portrait's label partly depends on *which* raters happened to see it. This
module fits the additive model

    score[image, rater] = mu + image_effect[image] + rater_offset[rater] + noise

using the image-residualized rater normal equations (sum of rater offsets = zero).
Rater offsets are shrunk toward zero with a penalty
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
    status: str = "estimated"
    components: int = 1
    residual_dof: int = 0

    def adjusted(self, low: float = 1.0, high: float = 7.0) -> dict[str, float]:
        values = np.clip(self.mean + self.image_effect, low, high)
        return {image: float(v) for image, v in zip(self.images, values, strict=True)}


def _index(
    ratings: Sequence[Rating],
) -> tuple[list[str], list[str], np.ndarray, np.ndarray, np.ndarray]:
    if not ratings:
        raise ValueError("No ratings")
    if len(ratings) > 100000 or any(not i.strip() or not r.strip() for i, r, _ in ratings):
        raise ValueError("Bounded ratings with nonempty image/rater identifiers required")
    images = sorted({r[0] for r in ratings})
    raters = sorted({r[1] for r in ratings})
    i_pos = {k: n for n, k in enumerate(images)}
    r_pos = {k: n for n, k in enumerate(raters)}
    ii = np.fromiter((i_pos[r[0]] for r in ratings), dtype=np.int64, count=len(ratings))
    rr = np.fromiter((r_pos[r[1]] for r in ratings), dtype=np.int64, count=len(ratings))
    y = np.fromiter((float(r[2]) for r in ratings), dtype=np.float64, count=len(ratings))
    if not np.isfinite(y).all() or np.any((y < 1) | (y > 7)):
        raise ValueError("Finite native 1–7 ratings required")
    pairs = set(zip(ii.tolist(), rr.tolist(), strict=True))
    if len(pairs) != len(ratings):
        raise ValueError("Each rater may contribute one primary rating per image")
    return images, raters, ii, rr, y


def _components(ii: np.ndarray, rr: np.ndarray, n_i: int, n_r: int) -> int:
    parent = list(range(n_i + n_r))

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, r in zip(ii, rr, strict=True):
        a, b = root(int(i)), root(n_i + int(r))
        parent[a] = b
    return len({root(i) for i in range(len(parent))})


def fit_rater_model(ratings: Sequence[Rating]) -> RaterModel:
    """Research candidate under an additive, exchangeable-rater, ignorable-missingness model.

    Residualizing image intercepts gives H=diag(n_r)-C.T diag(1/n_i) C.
    The exact noise contribution to Var(b_hat) is sigma² tr(H+)/ (R-1),
    not mean(sigma²/n_r), which ignores overlap and image/rater confounding.
    Disconnected, saturated or bounded-resource designs return raw means explicitly.
    The low-dimensional solve is capped at 256 raters/3000 images; no dense vote design.
    """
    images, raters, ii, rr, y = _index(ratings)
    n_i, n_r = len(images), len(raters)
    counts = np.bincount(ii, minlength=n_i)
    raw = np.bincount(ii, weights=y, minlength=n_i) / counts
    mu = float(y.mean())
    components = _components(ii, rr, n_i, n_r)
    dof = len(y) - n_i - n_r + components

    def fallback(status: str, noise: float = float("nan")) -> RaterModel:
        return RaterModel(
            images,
            raters,
            mu,
            raw - mu,
            np.zeros(n_r),
            counts,
            raw,
            noise,
            0.0,
            None,
            0,
            status,
            components,
            dof,
        )

    if components != 1:
        return fallback("disconnected")
    if dof <= 0 or n_r < 2:
        return fallback("insufficient_overlap")
    if n_r > 256 or n_i > 3000:
        return fallback("resource_limit")
    incidence = np.zeros((n_i, n_r))
    incidence[ii, rr] = 1.0  # Each image/rater pair was checked unique.
    cnt_r = np.bincount(rr, minlength=n_r)
    h = np.diag(cnt_r.astype(float)) - incidence.T @ (incidence / counts[:, None])
    rhs = np.bincount(rr, weights=y, minlength=n_r) - incidence.T @ raw
    values, vectors = np.linalg.eigh(h)
    keep = values > max(float(values.max()) * 1e-10, 1e-12)
    if int(keep.sum()) != n_r - 1:
        return fallback("insufficient_overlap")
    values, vectors = values[keep], vectors[:, keep]
    coordinates = vectors.T @ rhs
    offsets = vectors @ (coordinates / values)
    theta = raw - (incidence @ offsets) / counts
    residual = y - theta[ii] - offsets[rr]
    noise = float(residual @ residual / dof)
    variance = max(0.0, float(np.var(offsets, ddof=1) - noise * np.sum(1 / values) / (n_r - 1)))
    if variance <= 0:
        return fallback("no_detectable_rater_effect", noise)
    penalty = noise / variance
    offsets = vectors @ (coordinates / (values + penalty))
    theta = raw - (incidence @ offsets) / counts
    return RaterModel(
        images,
        raters,
        mu,
        theta - mu,
        offsets,
        counts,
        raw,
        noise,
        variance,
        penalty,
        1,
        "estimated",
        components,
        dof,
    )


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
    if not np.isfinite(r_half) or not -1 <= r_half <= 1 or not np.isfinite(m) or m < 1:
        raise ValueError("Valid correlation and equal half-panel size required")
    return r_half / (m - (m - 1.0) * r_half)


def projected(rho: float, k: float) -> float:
    if not np.isfinite(rho) or not 0 <= rho <= 1 or not np.isfinite(k) or k < 1:
        raise ValueError("Valid nonnegative reliability and panel size required")
    return k * rho / (1.0 + (k - 1.0) * rho)


def raters_needed(rho: float, target: float) -> int | None:
    if not 0 < rho < 1 or not 0 < target < 1:
        return None
    return int(np.ceil(target * (1 - rho) / (rho * (1 - target)) - 1e-9))


def reliability(
    ratings: Sequence[Rating], *, draws: int = 400, seed: int = 20261107, min_images: int = 10
) -> dict[str, Any]:
    """Split-half reliability with a bootstrap over images. Uses only images with >=2 ratings."""
    if (
        not isinstance(draws, int)
        or isinstance(draws, bool)
        or not 20 <= draws <= 2000
        or not isinstance(min_images, int)
        or min_images < 3
    ):
        raise ValueError("Use 20–2000 draws and at least three images")
    images, raters, ii, rr, y = _index(ratings)
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
        "method": "split-half conditional image resampling; restricted Spearman-Brown projection",
        "interval_scope": (
            "Descriptive conditional image resampling; no rater, subject-cluster "
            "or missingness uncertainty"
        ),
        "assumptions": (
            "Exchangeable independent raters, additive effects and ignorable "
            "assignment; not verified"
        ),
        "components": _components(ii, rr, len(images), len(raters)),
        "observed_half_correlation": None,
        "observed_half_interval": None,
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
        r_half, _ = result
        singles.append(r_half)
    if len(singles) < draws // 2:
        summary["status"] = "insufficient_variation"
        return summary
    values = np.asarray(singles)
    r = float(np.median(values))
    low, high = float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))
    summary.update(observed_half_correlation=r, observed_half_interval=[low, high])
    if summary["components"] != 1:
        summary["status"] = "disconnected"
        return summary
    if int(counts.min()) != int(counts.max()):
        summary["status"] = "unequal_coverage_no_projection"
        return summary
    if low <= 0:
        summary["status"] = "nonpositive_or_uncertain_agreement"
        return summary
    k = float(counts[0])
    m = float(int(k) // 2)
    rho = single_rater(r, m)
    summary.update(
        status="estimated",
        single_rater=rho,
        at_current_coverage=projected(rho, k),
        interval_95=[projected(single_rater(low, m), k), projected(single_rater(high, m), k)],
        raters_needed={str(t): raters_needed(rho, t) for t in (0.7, 0.8, 0.9)},
    )
    return summary
