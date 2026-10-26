"""Phase 6A mathematics, training protocol and checkpoint integrity.

All data here is generated in-process and labelled synthetic. It verifies code
correctness only and says nothing about real aesthetic prediction quality.
"""

import csv
import hashlib
import json
import os
from io import BytesIO

import numpy as np
import pytest
from aevyra_inference.aesthetic import (
    analyze,
    conformal_half_width,
    display_score,
    distribution_loss,
    expected_score,
    fit_scoring_head,
    normalize_votes,
    objective,
    rating_spread,
    softmax,
    spearman,
    split_by_subject,
)
from aevyra_inference.aesthetic_checkpoint import (
    SLUG,
    AestheticScoringEngine,
    DatasetEvidence,
    checkpoint_status,
    load_checkpoint,
    release_failures,
    write_checkpoint,
)
from aevyra_inference.aesthetic_train import main as train_main
from aevyra_inference.engine import EnginePolicyError, EngineRegistry
from aevyra_inference.extractors import BASELINE
from PIL import Image

EVIDENCE = {
    "name": "Generated synthetic fixture",
    "license": "Test-only generated data",
    "terms_url": "https://example.invalid/test-only",
    "authorization_reference": "TEST-ONLY",
    "reviewer": "automated test",
    "annotator_population": "simulated raters",
    "adult_subjects_confirmed": True,
    "rating_scale": "five ordered categories, 1 (lowest) to 5 (highest)",
    "synthetic": True,
}


def synthetic(subjects=40, per_subject=3, d=230, raters=25, seed=0):
    """Learnable generated data: votes are sampled counts, never derived from a mean."""
    rng = np.random.default_rng(seed)
    direction = rng.normal(0, 1, d)
    rows, votes, ids = [], [], []
    for subject in range(subjects):
        base = rng.normal(0, 1, d)
        for _ in range(per_subject):
            x = base + rng.normal(0, 0.3, d)
            quality = float(x @ direction) / np.linalg.norm(direction)
            logits = -0.8 * (np.arange(1, 6) - (3 + 1.2 * quality)) ** 2
            p = np.exp(logits - logits.max())
            votes.append(rng.multinomial(raters, p / p.sum()))
            rows.append(x)
            ids.append(f"subject-{subject}")
    return np.asarray(rows), np.asarray(votes, dtype=float), ids


def test_softmax_is_stable_and_normalized():
    p = softmax(np.array([[1000.0, 1000.0, 0, 0, 0], [-5, 0, 5, 1, 2]]))
    assert np.allclose(p.sum(axis=1), 1)
    assert np.allclose(p[0, :2], 0.5)


def test_votes_require_real_counts():
    assert np.allclose(normalize_votes(np.array([[1, 1, 2, 0, 0]])), [[0.25, 0.25, 0.5, 0, 0]])
    for bad in ([[1, 2, 3, 4]], [[0, 0, 0, 0, 0]], [[1, -1, 2, 0, 0]], [[np.nan, 1, 1, 1, 1]]):
        with pytest.raises(ValueError):
            normalize_votes(np.array(bad, dtype=float))


def test_distribution_loss_formula_and_gradient_match_finite_differences():
    rng = np.random.default_rng(3)
    z = rng.normal(0, 1, (4, 5))
    q = normalize_votes(rng.integers(0, 9, (4, 5)) + 1)
    p = softmax(z)
    loss, grad = distribution_loss(p, q)
    manual = np.mean(
        [np.mean([(p[n, : k + 1] - q[n, : k + 1]).sum() ** 2 for k in range(5)]) for n in range(4)]
    )
    assert loss == pytest.approx(manual)
    numeric = np.zeros_like(z)
    h = 1e-6
    for i in np.ndindex(z.shape):
        up, down = z.copy(), z.copy()
        up[i] += h
        down[i] -= h
        numeric[i] = (
            distribution_loss(softmax(up), q)[0] - distribution_loss(softmax(down), q)[0]
        ) / (2 * h)
    assert np.allclose(grad, numeric, atol=1e-8, rtol=1e-5)


def test_training_objective_gradients_including_weight_decay():
    rng = np.random.default_rng(4)
    x = rng.normal(0, 1, (6, 3))
    q = normalize_votes(rng.integers(1, 6, (6, 5)))
    w, b = rng.normal(0, 0.5, (3, 5)), rng.normal(0, 0.5, 5)
    _, grad_w, grad_b = objective(x, q, w, b, 0.1)
    h = 1e-6
    for target, grad in ((w, grad_w), (b, grad_b)):
        numeric = np.zeros_like(target)
        for i in np.ndindex(target.shape):
            original = target[i]
            target[i] = original + h
            up = objective(x, q, w, b, 0.1)[0]
            target[i] = original - h
            down = objective(x, q, w, b, 0.1)[0]
            target[i] = original
            numeric[i] = (up - down) / (2 * h)
        assert np.allclose(grad, numeric, atol=1e-8, rtol=1e-5)


def test_expected_and_display_score_endpoints():
    one_hot = np.eye(5)
    assert np.allclose(expected_score(one_hot), [1, 2, 3, 4, 5])
    assert np.allclose(display_score(expected_score(one_hot)), [1, 3.25, 5.5, 7.75, 10])
    assert np.allclose(rating_spread(one_hot), 0)
    assert rating_spread(np.array([[0.5, 0, 0, 0, 0.5]]))[0] == pytest.approx(2)


def test_subject_split_is_disjoint_deterministic_and_bounded():
    ids = [f"s{i // 2}" for i in range(40)]
    train, val, test = split_by_subject(ids)
    groups = [{ids[i] for i in part} for part in (train, val, test)]
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert len(train) + len(val) + len(test) == 40 and len(groups[2]) == 4
    assert all(
        np.array_equal(a, b) for a, b in zip(split_by_subject(ids), (train, val, test), strict=True)
    )
    with pytest.raises(ValueError, match="15 independent"):
        split_by_subject([f"s{i}" for i in range(14)])
    with pytest.raises(ValueError, match="Missing"):
        split_by_subject(["a"] * 20 + [" "])


def test_training_normalization_and_selection_never_see_test_subjects():
    x, votes, ids = synthetic()
    head, metrics = fit_scoring_head(x, votes, ids, epochs=60)
    train, _, test = split_by_subject(ids)
    assert np.allclose(head.mean, x[train].mean(axis=0))
    assert metrics["split"]["test"] == test.tolist()
    changed_x, changed_votes = x.copy(), votes.copy()
    changed_x[test] += 50.0
    changed_votes[test] = changed_votes[test][:, ::-1]
    other, other_metrics = fit_scoring_head(changed_x, changed_votes, ids, epochs=60)
    assert np.array_equal(head.weights, other.weights) and np.array_equal(head.mean, other.mean)
    assert other_metrics["test_mae"] != metrics["test_mae"]  # Only evaluation changed.


def test_learnable_signal_beats_simple_baselines_with_ranking_and_calibration():
    x, votes, ids = synthetic(subjects=200)
    _, metrics = fit_scoring_head(x, votes, ids)
    assert metrics["test_mae"] < metrics["mean_baseline_mae"]
    assert metrics["test_distribution_loss"] < metrics["mean_distribution_baseline_loss"]
    assert metrics["test_spearman"] > 0.5
    assert metrics["calibration"]["half_width_display"] > 0
    assert 0 <= metrics["calibration"]["test_coverage"] <= 1
    assert metrics["test_subjects"] == 40 and metrics["training_subjects"] == 120


def test_training_input_requirements():
    x, votes, ids = synthetic(subjects=20, per_subject=3)
    with pytest.raises(ValueError, match="60 labeled"):
        fit_scoring_head(x[:59], votes[:59], ids[:59])
    with pytest.raises(ValueError, match="variation"):
        fit_scoring_head(x, np.tile([0, 0, 5, 0, 0], (60, 1)), ids)
    with pytest.raises(ValueError, match="dimensions"):
        fit_scoring_head(x, votes[:-1], ids)
    with pytest.raises(ValueError, match="optimization"):
        fit_scoring_head(x, votes, ids, learning_rate=0)


def test_ranking_and_conformal_helpers():
    assert spearman(np.array([1.0, 2, 3, 4]), np.array([10.0, 20, 30, 40])) == pytest.approx(1)
    assert spearman(np.array([1.0, 1, 1]), np.array([1.0, 2, 3])) is None
    assert spearman(np.array([1.0, 2, 2, 3]), np.array([1.0, 2, 2, 3])) == pytest.approx(1)
    errors = np.arange(1, 20, dtype=float)
    assert conformal_half_width(errors, 0.9) == 18  # ceil(20 * 0.9) = 18th smallest.
    assert conformal_half_width(np.array([1.0, 2.0]), 0.9) is None


def test_analysis_separates_annotator_spread_from_score():
    x, votes, ids = synthetic()
    head, _ = fit_scoring_head(x, votes, ids, epochs=30)
    result = analyze(head, x[0])
    assert sum(result["rating_distribution"]) == pytest.approx(1)
    assert 1 <= result["score_10"] <= 10
    assert result["score_10"] == pytest.approx(1 + 2.25 * (result["expected_rating_5"] - 1))
    assert result["rating_spread_10"] == pytest.approx(2.25 * result["rating_spread_5"])
    assert head.predict(x[:2])["score"][0] == pytest.approx(result["score_10"])


def published(tmp_path, *, synthetic_data=True, version="test-v1"):
    x, votes, ids = synthetic(subjects=200)
    head, metrics = fit_scoring_head(x, votes, ids)
    evidence = DatasetEvidence.model_validate({**EVIDENCE, "synthetic": synthetic_data})
    item, sha = write_checkpoint(
        tmp_path,
        head,
        model_version=version,
        extractor=BASELINE,
        dataset=evidence,
        training={"seed": 42},
        metrics=metrics,
    )
    return item, sha, x


def test_checkpoint_round_trip_is_immutable_and_exact(tmp_path):
    item, sha, x = published(tmp_path)
    loaded = load_checkpoint(tmp_path, "test-v1", sha)
    assert (
        loaded.manifest == item
        and loaded.manifest.calibration.version == "test-v1+split-conformal-90"
    )
    directory = tmp_path / "aesthetic" / "test-v1"
    assert {p.name: p.stat().st_mode & 0o777 for p in directory.iterdir()} == {
        "head.f64": 0o444,
        "manifest.json": 0o444,
    }
    assert analyze(loaded.head, x[0])["score_10"] == pytest.approx(
        analyze(loaded.head, x[0].copy())["score_10"]
    )
    with pytest.raises(FileExistsError):
        published(tmp_path)
    with pytest.raises(ValueError):
        load_checkpoint(tmp_path, "../escape", sha)
    with pytest.raises(ValueError, match="manifest checksum"):
        load_checkpoint(tmp_path, "test-v1", "0" * 64)


def tampered(tmp_path, name, change):
    directory = tmp_path / "aesthetic" / "test-v1"
    directory.chmod(0o700)
    path = directory / name
    path.chmod(0o600)
    path.write_bytes(change(path.read_bytes()))
    return path


def test_weight_tampering_is_detected(tmp_path):
    _, sha, _ = published(tmp_path)
    tampered(tmp_path, "head.f64", lambda data: data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ValueError, match="weight checksum"):
        load_checkpoint(tmp_path, "test-v1", sha)
    status = checkpoint_status(tmp_path, "test-v1", sha, enabled=True, allow_synthetic=True)
    assert (status.available, status.reason, status.checkpoint) == (
        False,
        "checkpoint_integrity_failure",
        None,
    )


def test_feature_version_mismatch_is_rejected_even_when_repinned(tmp_path):
    published(tmp_path)
    path = tampered(
        tmp_path,
        "manifest.json",
        lambda data: json.dumps(
            {
                **json.loads(data),
                "representation": {"id": BASELINE, "dimension": 230, "preprocessing": "v2"},
            }
        ).encode(),
    )
    with pytest.raises(ValueError, match="Invalid checkpoint manifest"):
        load_checkpoint(tmp_path, "test-v1", hashlib.sha256(path.read_bytes()).hexdigest())


def test_status_requires_enablement_pin_and_release_gate(tmp_path):
    _, sha, _ = published(tmp_path)
    assert checkpoint_status(tmp_path, "test-v1", sha, enabled=False).reason == "disabled"
    assert (
        checkpoint_status(tmp_path, None, None, enabled=True).reason == "checkpoint_not_configured"
    )
    assert checkpoint_status(tmp_path, "test-v2", sha, enabled=True).reason == "checkpoint_missing"
    gated = checkpoint_status(tmp_path, "test-v1", sha, enabled=True)
    assert (gated.available, gated.reason) == (False, "validation_gate_failed")
    assert release_failures(gated.checkpoint.manifest) == ["synthetic_dataset"]
    ready = checkpoint_status(tmp_path, "test-v1", sha, enabled=True, allow_synthetic=True)
    assert (ready.available, ready.reason) == (True, "ready")


def test_release_gate_rejects_models_that_do_not_beat_baselines(tmp_path):
    rng = np.random.default_rng(9)
    x = rng.normal(0, 1, (90, 230))
    votes = rng.multinomial(20, [0.2] * 5, size=90).astype(float)
    ids = [f"s{i // 3}" for i in range(90)]
    head, metrics = fit_scoring_head(x, votes, ids, epochs=80)
    item, _ = write_checkpoint(
        tmp_path,
        head,
        model_version="noise",
        extractor=BASELINE,
        dataset=DatasetEvidence.model_validate({**EVIDENCE, "synthetic": False}),
        training={},
        metrics=metrics,
    )
    failures = release_failures(item)
    assert "synthetic_dataset" not in failures
    assert {"insufficient_ranking_correlation", "does_not_beat_mean_baseline"} & set(failures)


def test_engine_is_research_only_and_policy_gated(tmp_path):
    _, sha, x = published(tmp_path)
    loaded = load_checkpoint(tmp_path, "test-v1", sha)
    with pytest.raises(ValueError, match="dimension"):
        AestheticScoringEngine(loaded, [0.0] * 10, release_ready=True)
    engine = AestheticScoringEngine(loaded, x[0].tolist(), release_ready=False)
    info = engine.metadata()
    assert (info.slug, info.commercial_allowed, info.research_allowed, info.synthetic) == (
        SLUG,
        False,
        True,
        True,
    )
    registry = EngineRegistry([engine])
    with pytest.raises(EnginePolicyError):
        registry.score(SLUG, b"", production=True, purpose="research")
    with pytest.raises(EnginePolicyError):
        EngineRegistry([AestheticScoringEngine(loaded, x[0].tolist(), release_ready=True)]).score(
            SLUG, b"", production=True, purpose="commercial"
        )
    result = EngineRegistry(
        [AestheticScoringEngine(loaded, x[0].tolist(), release_ready=True)]
    ).score(SLUG, b"", production=True, purpose="research")
    assert result.display_score == pytest.approx(engine.analysis()["score_10"])
    assert result.raw_score == pytest.approx(engine.analysis()["expected_rating_5"])
    assert result.synthetic is True


def write_dataset(tmp_path, rows):
    images = tmp_path / "images"
    images.mkdir()
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["image", "subject_id", "votes_1", "votes_2", "votes_3", "votes_4", "votes_5"]
        )
        for name, subject, color, votes in rows:
            buffer = BytesIO()
            Image.new("RGB", (48, 48), color).save(buffer, "PNG")
            (images / name).write_bytes(buffer.getvalue())
            writer.writerow([name, subject, *votes])
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(EVIDENCE))
    return labels, images, plan


def test_training_command_publishes_checkpoint_from_vote_counts(tmp_path, capsys):
    rows = []
    for i in range(66):
        level = i % 5
        votes = [0] * 5
        votes[level] = 4
        votes[min(4, level + 1)] += 1
        rows.append((f"{i}.png", f"subject-{i // 3}", (40 * level + i, 30 + i, 90), votes))
    labels, images, plan = write_dataset(tmp_path, rows)
    code = train_main(
        [
            "--labels",
            str(labels),
            "--images",
            str(images),
            "--plan",
            str(plan),
            "--model-version",
            "cli-v1",
            "--model-root",
            str(tmp_path / "models"),
            "--extractor",
            BASELINE,
            "--epochs",
            "40",
        ]
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert "synthetic_dataset" in summary["release_failures"]
    assert "split" not in summary["metrics"]
    loaded = load_checkpoint(tmp_path / "models", "cli-v1", summary["manifest_sha256"])
    assert loaded.manifest.training["votes_per_image_min"] == 5


def test_training_command_refuses_mean_scores_and_traversal(tmp_path, capsys):
    labels, images, plan = write_dataset(tmp_path, [("a.png", "s", "red", [1, 1, 1, 1, 1])])
    labels.write_text("image,subject_id,mean_score\na.png,s,3.2\n")
    args = [
        "--labels",
        str(labels),
        "--images",
        str(images),
        "--plan",
        str(plan),
        "--model-version",
        "x",
        "--model-root",
        str(tmp_path / "m"),
        "--extractor",
        BASELINE,
    ]
    assert train_main(args) == 1
    assert "real vote counts" in capsys.readouterr().err
    labels.write_text(
        "image,subject_id,votes_1,votes_2,votes_3,votes_4,votes_5\n../plan.json,s,1,1,1,1,1\n"
    )
    assert train_main(args) == 1
    labels.write_text(
        "image,subject_id,votes_1,votes_2,votes_3,votes_4,votes_5\na.png,s,1,0,0,0,0\n"
    )
    assert train_main(args) == 1
    assert "at least 3 real ratings" in capsys.readouterr().err
    plan.write_text(json.dumps({**EVIDENCE, "adult_subjects_confirmed": False}))
    assert train_main(args) == 2
    assert not (tmp_path / "m").exists()
    assert os.listdir(images) == ["a.png"]
