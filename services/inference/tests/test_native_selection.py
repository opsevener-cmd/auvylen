"""Grouped-CV ridge selection. Generated fixtures only; never human-accuracy evidence."""

import csv

import numpy as np
import pytest
from aevyra_inference.aesthetic import split_by_subject
from aevyra_inference.native import effective_dof, fit_head, select_model
from aevyra_inference.native_dev_study import development_table
from aevyra_inference.native_selection import (
    ALPHA_GRID,
    RidgePath,
    cv_curve,
    grouped_folds,
    select_alpha,
)


def data(n=120, d=40, seed=3):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, d)) * rng.uniform(0.1, 3, d)
    y = np.clip(4 + x[:, 0] * 0.4 + rng.normal(0, 0.5, n), 1, 7)
    subjects = [f"person-{i // 2}" for i in range(n)]
    return x, y, subjects


def test_ridge_path_matches_the_existing_solver_for_every_penalty():
    rng = np.random.default_rng(0)
    for n, d in [(60, 300), (150, 40)]:
        x, y = rng.normal(size=(n, d)) * rng.uniform(0.01, 3, d), 1 + 6 * rng.random(n)
        path = RidgePath.fit(x, y)
        for alpha in (0.01, 1.0, 100.0, 1e4):
            reference = fit_head(x, y, alpha, 7)
            assert np.allclose(path.weights(alpha), reference.weights, atol=1e-10)
            assert np.allclose(path.head(alpha, 7).predict(x), reference.predict(x), atol=1e-10)
    with pytest.raises(ValueError):
        path.weights(0)


def test_grouped_folds_keep_people_together_and_cover_each_once_per_repeat():
    subjects = [f"s{i // 3}" for i in range(60)]
    folds = grouped_folds(subjects, 5, seed=7, repeats=2)
    assert len(folds) == 10
    for repeat in range(2):
        held = np.concatenate([h for _, h in folds[repeat * 5 : repeat * 5 + 5]])
        assert sorted(held) == list(range(60))
    for train, held in folds:
        assert not {subjects[i] for i in train} & {subjects[i] for i in held}
    assert all(
        np.array_equal(a[1], b[1])
        for a, b in zip(folds, grouped_folds(subjects, 5, seed=7, repeats=2), strict=True)
    )
    with pytest.raises(ValueError):
        grouped_folds(["a", "b"], 5, seed=1)


def test_selection_prefers_the_stronger_penalty_on_exact_ties():
    assert select_alpha({0.1: 0.5, 10.0: 0.5, 1.0: 0.6}) == 10.0
    assert select_alpha({0.1: 0.4, 10.0: 0.5}) == 0.1


def test_cv_curve_rejects_misaligned_augmentation():
    x, y, subjects = data()
    with pytest.raises(ValueError):
        cv_curve(x, y, subjects, rating_max=7, views=np.zeros((2, 3, x.shape[1])))
    curve = cv_curve(x, y, subjects, rating_max=7, repeats=1, views=np.stack([x, x]))
    assert set(curve) == set(ALPHA_GRID) and all(np.isfinite(list(curve.values())))


def test_effective_dof_flags_near_interpolation():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(60, 1024))
    assert effective_dof(x, 0.01) > 58  # ~rank: the .01 penalty barely regularizes.
    assert effective_dof(x, 1e5) < 1


def test_default_protocol_unchanged_and_reports_diagnostics():
    x, y, subjects = data()
    _, head, report = select_model({"enc": x}, y, subjects, rating_max=7)
    train, _, _ = split_by_subject(subjects, 42)
    alpha = report["selected_alpha"]
    assert np.array_equal(head.weights, fit_head(x[train], y[train], alpha, 7).weights)
    assert report["selection_protocol"] == "validation-3"
    assert report["distinct_training_images"] == len(train)
    assert 0 < report["effective_degrees_of_freedom"] <= len(train)


def test_grouped_cv_never_uses_sealed_test_labels():
    x, y, subjects = data()
    _, _, test = split_by_subject(subjects, 42)
    winner, head, report = select_model(
        {"enc": x}, y, subjects, rating_max=7, selection="grouped-cv"
    )
    changed = y.copy()
    changed[test] = 8 - changed[test]  # Reverse every sealed test label.
    winner2, head2, report2 = select_model(
        {"enc": x}, changed, subjects, rating_max=7, selection="grouped-cv"
    )
    assert (winner, report["selected_alpha"]) == (winner2, report2["selected_alpha"])
    assert np.array_equal(head.weights, head2.weights)
    assert report["test"] != report2["test"]  # Only the final evaluation changed.
    assert report["selection_protocol"] == "grouped-cv"
    assert report["selected_alpha"] in ALPHA_GRID
    assert report["partition_sizes"]["fitted_development"] == len(y) - len(test)
    with pytest.raises(ValueError):
        select_model({"enc": x}, y, subjects, rating_max=7, selection="unknown")  # type: ignore[arg-type]


def test_development_table_drops_sealed_rows_before_parsing_ratings(tmp_path):
    source = tmp_path / "means.csv"
    subjects = [f"{i:03}" for i in range(100)]
    _, _, test = split_by_subject(subjects, 42)
    sealed = {subjects[i] for i in test}
    with source.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"])
        for subject in subjects:
            # Sealed rows carry unparseable ratings: the study must never need to read them.
            rating = "SEALED-NOT-READ" if subject in sealed else "4.0"
            writer.writerow([f"{subject}.jpg", subject, rating, 3, "r", "c"])
    destination = tmp_path / "development.csv"
    sizes = development_table(source, 42, destination)
    assert sizes == {"development_images": 80, "sealed_test_subjects_excluded": 20}
    rows = list(csv.DictReader(destination.open()))
    assert len(rows) == 80 and not {r["subject_id"] for r in rows} & sealed
    assert all(r["rating"] == "4.0" for r in rows)
    assert oct(destination.stat().st_mode & 0o777) == "0o600"


def test_training_run_supports_grouped_cv_end_to_end(tmp_path):
    from aevyra_inference.extractors import BASELINE
    from aevyra_inference.native_checkpoint import load, write
    from aevyra_inference.native_train import run
    from test_native import fixture, plan

    labels, images = fixture(tmp_path)
    head, item = run(labels, images, plan(), tmp_path, encoders=(BASELINE,), selection="grouped-cv")
    assert item.report["selection_protocol"] == "grouped-cv"
    assert "grouped development CV" in item.report["test_policy"]
    pin = write(tmp_path / "checkpoint", head, item)
    restored, _ = load(tmp_path / "checkpoint", pin, require_release=False)
    assert np.array_equal(restored.weights, head.weights)
