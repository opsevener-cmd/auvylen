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


def test_unbalanced_adjustment_matches_declared_penalized_least_squares():
    rng = np.random.default_rng(97)
    rows = []
    for i in range(30):
        for r in range(5):
            if r == 0 or rng.random() < 0.35:
                rows.append(
                    (
                        f"i{i}",
                        f"r{r}",
                        4 + 0.02 * i + [-0.8, 0.6, 0.5, -0.4, 0.2][r] + rng.normal(0, 0.1),
                    )
                )
    model = fit_rater_model(rows)
    assert model.status == "estimated"
    ip = {v: k for k, v in enumerate(model.images)}
    rp = {v: k for k, v in enumerate(model.raters)}
    design = np.zeros((len(rows), len(ip) + len(rp)))
    for j, (i, r, _) in enumerate(rows):
        design[j, ip[i]] = 1
        design[j, len(ip) + rp[r]] = 1
    penalty = np.zeros((len(rp), design.shape[1]))
    penalty[:, len(ip) :] = np.eye(len(rp)) * np.sqrt(model.shrinkage)
    reference = np.linalg.lstsq(
        np.vstack([design, penalty]), np.r_[[y for _, _, y in rows], np.zeros(len(rp))], rcond=None
    )[0]
    np.testing.assert_allclose(model.mean + model.image_effect, reference[: len(ip)], atol=1e-9)
    np.testing.assert_allclose(model.rater_offset, reference[len(ip) :], atol=1e-9)
    assert abs(model.rater_offset.sum()) < 1e-9


def test_disconnected_saturated_and_resource_bound_designs_return_raw_means():
    rows = [
        (f"{c}-i{i}", f"{c}-r{r}", 3 + 0.05 * i + r)
        for c in range(2)
        for i in range(12)
        for r in range(3)
    ]
    model = fit_rater_model(rows)
    assert model.status == "disconnected" and model.components == 2
    np.testing.assert_allclose(list(model.adjusted().values()), model.raw_mean)
    assert fit_rater_model([("i", "r", 4)]).status == "insufficient_overlap"
    rows = [(f"i{i}", f"r{r}", 3 + i % 2 + r % 2) for i in range(3) for r in range(257)]
    assert fit_rater_model(rows).status == "resource_limit"


def test_heterogeneous_missingness_reports_observed_agreement_without_false_projection():
    _, rows = simulate(15, images=80, raters=20, k=8)
    # Retain different panel sizes. Using their mean in a nonlinear inversion is invalid.
    counts = {}
    uneven = []
    for i, r, y in rows:
        counts[i] = counts.get(i, 0) + 1
        if counts[i] <= (2 if int(i[1:]) % 2 else 8):
            uneven.append((i, r, y))
    result = reliability(uneven, draws=40)
    assert result["status"] == "unequal_coverage_no_projection"
    assert result["observed_half_interval"] is not None
    assert result["single_rater"] is None and result["interval_95"] is None
    assert all(v is None for v in result["raters_needed"].values())


def test_invalid_parameters_and_out_of_scale_votes_are_rejected():
    rows = [(f"i{i}", f"r{r}", 4) for i in range(20) for r in range(3)]
    with pytest.raises(ValueError):
        reliability(rows, draws=0)
    with pytest.raises(ValueError):
        fit_rater_model([("i", "r", 8)])
    with pytest.raises(ValueError):
        fit_rater_model([("", "r", 4)])
    with pytest.raises(ValueError):
        projected(-0.1, 3)


def test_negative_half_agreement_is_not_replaced_by_zero():
    rows = [(f"i{i}", "a", float(1 + i % 7)) for i in range(30)]
    rows += [(f"i{i}", "b", float(7 - i % 7)) for i in range(30)]
    result = reliability(rows, draws=40)
    assert result["status"] == "nonpositive_or_uncertain_agreement"
    assert result["observed_half_correlation"] == pytest.approx(-1)
    assert result["single_rater"] is None and result["interval_95"] is None
