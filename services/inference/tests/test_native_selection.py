"""Grouped-CV ridge selection. Generated fixtures only; never human-accuracy evidence."""

import csv
import hashlib

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
    assert effective_dof(x, 1e5) < 2  # Includes the unpenalized intercept.


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


def test_development_table_drops_sealed_rows_before_parsing_ratings(tmp_path, monkeypatch):
    source = tmp_path / "means.csv"
    subjects = [f"{i:03}" for i in range(100)]
    monkeypatch.setattr(
        "aevyra_inference.native_dev_study.LONDON_SUBJECTS_SHA256",
        hashlib.sha256("\n".join(subjects).encode()).hexdigest(),
    )
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
    with pytest.raises(ValueError, match="cannot be changed"):
        development_table(source, 77, tmp_path / "wrong-seed.csv")

    # Changing experimental seeds must not redefine the excluded people.
    import aevyra_inference.native_dev_study as module
    from test_native import plan

    def development_loader(path, *_):
        filtered = list(csv.DictReader(path.open()))
        assert len(filtered) == 80
        assert not {r["subject_id"] for r in filtered} & sealed
        assert all(r["rating"] == "4.0" for r in filtered)
        raise RuntimeError("reached development only")

    monkeypatch.setattr(module, "load_rows", development_loader)
    with pytest.raises(RuntimeError, match="reached development only"):
        module.study(source, tmp_path, plan(), tmp_path, [], seed=77)
    # Dropping subjects must not move the cutoff of the hash-based sealed partition.
    lines = source.read_text().splitlines()
    source.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="registry changed"):
        development_table(source, 42, tmp_path / "subset.csv")


def test_training_run_supports_grouped_cv_end_to_end(tmp_path):
    from aevyra_inference.extractors import BASELINE
    from aevyra_inference.native_checkpoint import load, write
    from aevyra_inference.native_train import run
    from test_native import fixture, plan

    labels, images = fixture(tmp_path)
    head, item = run(labels, images, plan(), tmp_path, encoders=(BASELINE,), selection="grouped-cv")
    assert item.report["selection_protocol"] == "grouped-cv"
    assert item.report["fitted_design_rows"] == 3 * item.report["distinct_training_images"]
    assert "grouped development CV" in item.report["test_policy"]
    pin = write(tmp_path / "checkpoint", head, item)
    restored, _ = load(tmp_path / "checkpoint", pin, require_release=False)
    assert np.array_equal(restored.weights, head.weights)


def test_effective_dof_matches_hat_matrix_including_intercept():
    x, _, _ = data(n=11, d=4)
    alpha = 0.7
    z = (x - x.mean(0)) / np.maximum(x.std(0), 0.05)
    smoother = np.ones((len(x), len(x))) / len(x) + z @ np.linalg.solve(
        z.T @ z + alpha * np.eye(x.shape[1]), z.T
    )
    assert effective_dof(x, alpha) == pytest.approx(np.trace(smoother))
    assert effective_dof(np.ones((10, 4)), alpha) == pytest.approx(1)


@pytest.mark.parametrize("bad", ["subjects", "labels", "blank_subject", "empty_grid", "scale"])
def test_cv_refuses_misaligned_or_invalid_selection_inputs(bad):
    x, y, subjects = data()
    kwargs = {"rating_max": 7}
    if bad == "subjects":
        subjects = subjects[:-2]
    elif bad == "labels":
        y = y[:-2]
    elif bad == "blank_subject":
        subjects[0] = " "
    elif bad == "empty_grid":
        kwargs["alphas"] = ()
    else:
        kwargs["rating_max"] = 10
    with pytest.raises(ValueError, match="Aligned finite"):
        cv_curve(x, y, subjects, **kwargs)


def test_training_refuses_unknown_protocol_before_reading_data(tmp_path, monkeypatch):
    import aevyra_inference.native_train as training
    from test_native import plan

    def forbidden(*_):
        raise AssertionError("Must not read data")

    monkeypatch.setattr(training, "load_rows", forbidden)
    with pytest.raises(ValueError, match="Unknown selection"):
        training.run(tmp_path, tmp_path, plan(), tmp_path, selection="grouped_cv_typo")


def test_grouped_checkpoint_cannot_enter_original_london_replay(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from aevyra_inference import native_london_evaluate as replay

    item = SimpleNamespace(
        collection=SimpleNamespace(synthetic=False), report={"selection_protocol": "grouped-cv"}
    )
    monkeypatch.setattr(replay, "load", lambda *a, **kw: (None, item))

    def forbidden(*a):
        raise AssertionError("Replay must not touch labels")

    monkeypatch.setattr(replay, "load_rows", forbidden)
    with pytest.raises(ValueError, match="original validation-selected"):
        replay.evaluate(tmp_path, tmp_path, "a" * 64, tmp_path)
