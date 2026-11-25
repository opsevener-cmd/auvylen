"""Paired, subject-grouped development CV with a decision rule fixed before any real run.

Outer folds and seeds are identical to the earlier CPU research (``42 + 1000 + repeat``),
so the MobileNet reference reproduces previously reported development aggregates.

PRE-REGISTERED DECISION RULE (do not edit after the first London run; see ledger):
* Reference: ``mobilenetv3-small`` + pilot ridge rule (``ridge``).
* A candidate is promotable only if its encoder is deployable AND
  (1) the paired bootstrap interval of MAE(candidate) - MAE(reference), at two-sided
      level 0.05 / k (Bonferroni over the k deployable candidates), lies entirely < 0, and
  (2) its mean repeat Spearman is >= the reference's.
* Among promotable candidates, choose the lowest MAE. If none, the reference stays.
* Research-only encoders are reported but never promoted.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from auvylen7b.encoders import ENCODERS
from auvylen7b.heads import PENALTIES, cross_entropy, earth_movers, fit_distribution
from auvylen7b.store import Store, key

OUTER_REPEATS = 5
REFERENCE = "mobilenetv3-small/ridge"


def _metrics(predicted: np.ndarray, y: np.ndarray) -> dict[str, float]:
    from aevyra_inference.aesthetic import spearman

    return {
        "mae": float(np.abs(predicted - y).mean()),
        "rmse": float(np.sqrt(((predicted - y) ** 2).mean())),
        "spearman": float(spearman(predicted, y)),
    }


def _distribution_candidate(x, views, targets, subjects, train):
    """Choose the penalty by inner grouped CV (cross-entropy), then refit on all training rows."""
    from aevyra_inference.native_selection import grouped_folds

    inner_subjects = [subjects[i] for i in train]
    scores = {p: [] for p in PENALTIES}
    for fit, held in grouped_folds(inner_subjects, 5, seed=42):
        rows = train[fit]
        tx = np.concatenate([x[rows], *views[:, rows]])
        ty = np.tile(targets[rows], (len(views) + 1, 1))
        for penalty in PENALTIES:
            head = fit_distribution(tx, ty, penalty)
            scores[penalty].append(
                cross_entropy(head.distribution(x[train[held]]), targets[train[held]])
            )
    penalty = min(PENALTIES, key=lambda p: (np.mean(scores[p]), -p))
    tx = np.concatenate([x[train], *views[:, train]])
    return fit_distribution(tx, np.tile(targets[train], (len(views) + 1, 1)), penalty), penalty


def evaluate(store: Store, dataset, shards: dict[str, str], encoders: list[str]) -> dict[str, Any]:
    from aevyra_inference.native_dev_study import paired_bootstrap, protocol_a
    from aevyra_inference.native_selection import grouped_folds

    y = np.asarray([i.rating for i in dataset.items])
    targets = np.asarray([i.histogram for i in dataset.items])
    subjects = [i.subject for i in dataset.items]
    config = {
        "data": dataset.fingerprint,
        "shards": {k: shards[k] for k in sorted(shards)},
        "repeats": OUTER_REPEATS,
    }
    unit = key("evaluate", config)
    relative = f"results/{unit}.json"
    if store.exists(relative):
        return store.read_json(relative)
    features = {
        name: {
            kind: store.read_arrays(shards[f"{name}/{kind}"])["features"]
            for kind in ("clean", "lighting", "crop")
        }
        for name in encoders
    }
    runs: dict[str, list[np.ndarray]] = {}
    extra: dict[str, dict[str, list]] = {}
    for repeat in range(OUTER_REPEATS):
        predicted: dict[str, np.ndarray] = {}
        for train, held in grouped_folds(subjects, 5, seed=42 + 1000 + repeat):
            train, held = np.asarray(train), np.asarray(held)
            for name in encoders:
                f = features[name]
                views = np.stack([f["lighting"], f["crop"]])
                head, _ = protocol_a(
                    f["clean"][train],
                    views[:, train],
                    y[train],
                    [subjects[i] for i in train],
                    42,
                    7.0,
                )
                predicted.setdefault(f"{name}/ridge", np.empty(len(y)))[held] = head.predict(
                    f["clean"][held]
                )
                dist, penalty = _distribution_candidate(f["clean"], views, targets, subjects, train)
                predicted.setdefault(f"{name}/distribution", np.empty(len(y)))[held] = dist.predict(
                    f["clean"][held]
                )
                bucket = extra.setdefault(
                    f"{name}/distribution", {"emd": [], "ce": [], "penalty": []}
                )
                p = dist.distribution(f["clean"][held])
                bucket["emd"].append(earth_movers(p, targets[held]))
                bucket["ce"].append(cross_entropy(p, targets[held]))
                bucket["penalty"].append(penalty)
            base = np.tile(targets[train].mean(0), (len(held), 1))
            bucket = extra.setdefault("train-average-histogram", {"emd": [], "ce": []})
            bucket["emd"].append(earth_movers(base, targets[held]))
            bucket["ce"].append(cross_entropy(base, targets[held]))
            predicted.setdefault("train-mean", np.empty(len(y)))[held] = y[train].mean()
        for name, values in predicted.items():
            runs.setdefault(name, []).append(values)
    summary = {}
    for name, values in runs.items():
        scores = [_metrics(v, y) for v in values]
        summary[name] = {
            m: float(np.mean([s[m] for s in scores])) for m in ("mae", "rmse", "spearman")
        }
        if name in extra:
            summary[name].update(
                {
                    k: (sorted(set(v)) if k == "penalty" else float(np.mean(v)))
                    for k, v in extra[name].items()
                }
            )
    for name in ("train-average-histogram",):
        summary[name] = {k: float(np.mean(v)) for k, v in extra[name].items()}
    errors = {k: np.mean([np.abs(v - y) for v in vals], axis=0) for k, vals in runs.items()}
    candidates = [n for n in runs if n not in (REFERENCE, "train-mean")]
    deployable = [n for n in candidates if ENCODERS[n.split("/")[0]].deployable]
    alpha = 0.05 / max(len(deployable), 1)
    comparisons = {}
    for name in candidates:
        draws = paired_bootstrap(errors[REFERENCE], errors[name], subjects, 4000, 20261109)
        interval = _interval(errors[REFERENCE], errors[name], subjects, alpha)
        comparisons[name] = {**draws, "corrected_interval": interval, "corrected_level": 1 - alpha}
    promotable = [
        n
        for n in deployable
        if comparisons[n]["corrected_interval"][1] < 0
        and summary[n]["spearman"] >= summary[REFERENCE]["spearman"]
    ]
    winner = min(promotable, key=lambda n: summary[n]["mae"]) if promotable else REFERENCE
    result = {
        "dataset": dataset.name,
        "synthetic": dataset.synthetic,
        "subjects": len(set(subjects)),
        "provenance": dataset.provenance,
        "outer": f"subject-grouped 5-fold x {OUTER_REPEATS}, seeds 1042..1046",
        "summary": summary,
        "vs_reference": comparisons,
        "promotable": promotable,
        "decision": winner,
        "rule": "see auvylen7b/evaluate.py docstring (pre-registered)",
    }
    store.write_json(relative, result)
    store.record(unit, stage="evaluate", decision=winner, synthetic=dataset.synthetic)
    return result


def _interval(
    reference: np.ndarray, candidate: np.ndarray, subjects: list[str], alpha: float
) -> list[float]:
    """Subject-cluster percentile bootstrap of mean(candidate - reference) at level 1 - alpha."""
    unique = sorted(set(subjects))
    groups = [np.flatnonzero(np.asarray(subjects) == s) for s in unique]
    difference = candidate - reference
    rng = np.random.default_rng(20261109)
    draws = [
        float(
            np.mean(
                np.concatenate(
                    [difference[groups[i]] for i in rng.integers(0, len(groups), len(groups))]
                )
            )
        )
        for _ in range(4000)
    ]
    return [float(np.quantile(draws, alpha / 2)), float(np.quantile(draws, 1 - alpha / 2))]
