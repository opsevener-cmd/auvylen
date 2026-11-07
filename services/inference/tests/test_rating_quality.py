"""Simulated rating designs with known ground truth. Never evidence about real people."""

import numpy as np
import pytest
from aevyra_inference.rating_quality import (
    fit_rater_model,
    projected,
    raters_needed,
    reliability,
    single_rater,
)


def simulate(seed, *, images=300, raters=60, k=5, sd_image=0.8, sd_rater=0.7, crossed=False):
    rng = np.random.default_rng(seed)
    true = 4 + rng.normal(0, sd_image, images)
    offset = rng.normal(0, sd_rater, raters)
    rows = []
    for i in range(images):
        chosen = range(raters) if crossed else rng.choice(raters, k, replace=False)
        for r in chosen:
            # Integer 1–7 responses, like the real interface.
            score = int(np.clip(np.rint(true[i] + offset[r] + rng.normal(0, 1.0)), 1, 7))
            rows.append((f"i{i:04d}", f"r{r:03d}", score))
    return true, rows


def errors(seed, **kwargs):
    true, rows = simulate(seed, **kwargs)
    model = fit_rater_model(rows)
    truth = np.asarray([true[int(name[1:])] for name in model.images])
    adjusted = np.asarray(list(model.adjusted().values()))
    rmse = lambda v: float(np.sqrt(np.mean((v - truth) ** 2)))  # noqa: E731
    return rmse(model.raw_mean), rmse(adjusted)


def test_rater_adjustment_beats_plain_means_on_incomplete_designs():
    results = np.asarray([errors(seed) for seed in range(12)])
    assert (results[:, 1] < results[:, 0]).all()
    assert results[:, 1].mean() < 0.92 * results[:, 0].mean()


def test_fully_crossed_design_leaves_means_unchanged():
    _, rows = simulate(1, images=40, raters=8, crossed=True)
    model = fit_rater_model(rows)
    assert np.allclose(list(model.adjusted().values()), np.clip(model.raw_mean, 1, 7), atol=1e-6)


def test_no_rater_effect_keeps_labels_close_to_means():
    raw, adjusted = errors(3, sd_rater=0.0)
    assert abs(raw - adjusted) < 0.02


def test_labels_stay_on_native_scale_and_inputs_are_validated():
    _, rows = simulate(4, images=50, raters=10)
    values = fit_rater_model(rows).adjusted().values()
    assert all(1 <= v <= 7 for v in values)
    with pytest.raises(ValueError, match="one primary"):
        fit_rater_model([("a", "r", 3), ("a", "r", 4)])
    with pytest.raises(ValueError):
        fit_rater_model([])
    with pytest.raises(ValueError):
        fit_rater_model([("a", "r", float("nan"))])


def test_reliability_recovers_simulated_agreement_and_spearman_brown():
    _, rows = simulate(5, images=400, k=6)
    result = reliability(rows)
    assert result["status"] == "estimated"
    # Theory before integer rounding: 0.64 / (0.64 + 0.49 + 1.0) = 0.30; rounding attenuates.
    assert 0.2 < result["single_rater"] < 0.33
    low, high = result["interval_95"]
    assert low < result["at_current_coverage"] < high
    assert result["raters_needed"]["0.8"] > 6
    assert single_rater(projected(0.3, 4), 4) == pytest.approx(0.3)
    assert raters_needed(0.3, 0.8) == 10 and raters_needed(0, 0.8) is None


def test_reliability_refuses_to_guess_from_little_data():
    _, rows = simulate(6, images=6, raters=10, k=3)
    assert reliability(rows)["status"] == "insufficient_data"
    assert (
        reliability([(f"i{i}", f"r{r}", 4) for i in range(20) for r in range(3)])["status"]
        == "insufficient_variation"
    )
