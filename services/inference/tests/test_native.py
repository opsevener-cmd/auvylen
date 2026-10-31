"""Generated mathematical/image fixtures only. Never evidence of human aesthetic accuracy."""

import csv
import hashlib

import numpy as np
import pytest
from aevyra_inference.aesthetic import split_by_subject
from aevyra_inference.extractors import BASELINE
from aevyra_inference.native import fit_head, select_model
from aevyra_inference.native_checkpoint import NativeProvider, load, release_failures, write
from aevyra_inference.native_data import Collection, aggregate_annotations, load_rows
from aevyra_inference.native_train import run
from PIL import Image


def plan():
    return Collection(
        name="UNIT TEST ONLY",
        synthetic=True,
        encoder_rights_review="TEST",
        annotator_population="Mathematical fixture, not human raters",
        rating_protocol_reference="UNIT TEST ONLY",
        rights={
            "test": dict(
                image_license="TEST",
                annotation_license="TEST",
                subject_release="TEST",
                training_permission="TEST",
                derived_weight_permission="TEST",
                reviewer="TEST",
                adult_confirmed=True,
                research_allowed=True,
            )
        },
    )


def fixture(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"])
        for i in range(60):
            pixels = np.random.default_rng(i).integers(0, 256, (224, 224, 3), dtype=np.uint8)
            Image.fromarray(pixels).save(images / f"{i}.png")
            writer.writerow(
                [f"{i}.png", f"fixture-{i // 4}", 1 + (i % 5), 3, "test", "generated pixels"]
            )
    return labels, images


def test_regression_is_learned_and_statistics_are_train_only():
    rng = np.random.default_rng(5)
    x = rng.normal(size=(200, 4))
    y = np.clip(3 + x[:, 0] * 0.3, 1, 5)
    subjects = [f"math-{i}" for i in range(200)]
    train, val, test = split_by_subject(subjects)
    _, head, report = select_model({"math": x}, y, subjects)
    assert np.allclose(head.mean, x[train].mean(0))
    assert report["test"]["mae"] < report["mean_baseline"]["mae"]
    changed = y.copy()
    changed[test] = 1
    _, same, other = select_model({"math": x}, changed, subjects)
    assert np.array_equal(head.weights, same.weights)
    assert report["selected_alpha"] == other["selected_alpha"]
    assert not ({subjects[i] for i in train} & {subjects[i] for i in val})
    assert not ({subjects[i] for i in test} & {subjects[i] for i in val})
    with pytest.raises(ValueError):
        fit_head(x, y, float("nan"))
    with pytest.raises(ValueError):
        select_model({"math": x}, y, subjects, train_views={"math": x[None, :, :]})


def test_full_fixture_training_roundtrip_and_no_release(tmp_path, monkeypatch):
    labels, images = fixture(tmp_path)
    head, item = run(labels, images, plan(), tmp_path, encoders=(BASELINE,))
    assert "synthetic_data" in release_failures(item)
    assert "real_pose_review_missing" in release_failures(item)
    root = tmp_path / "checkpoint"
    pin = write(root, head, item)
    restored, _ = load(root, pin, require_release=False)
    assert np.array_equal(restored.weights, head.weights)
    monkeypatch.setenv("AUVYLEN_NATIVE_MANIFEST_SHA256", pin)
    assert not NativeProvider().availability(root).available
    with pytest.raises(ValueError):
        load(root, pin)
    with pytest.raises(ValueError):
        write(root, head, item)
    with pytest.raises(ValueError):
        load(root, "0" * 64, require_release=False)
    raw = (root / "head.f64").read_bytes()
    (root / "head.f64").write_bytes(raw[:-8] + b"\0" * 8)
    with pytest.raises(ValueError):
        load(root, pin, require_release=False)


def test_annotation_rights_paths_and_duplicate_pixels(tmp_path):
    labels, images = fixture(tmp_path)
    missing = plan().model_copy(update={"rights": {}})
    with pytest.raises(ValueError, match="rights"):
        load_rows(labels, images, missing)
    text = labels.read_text()
    labels.write_text(text.replace("0.png", "../outside.png", 1))
    with pytest.raises(ValueError, match="relative"):
        load_rows(labels, images, plan())
    labels.write_text(text)
    (images / "1.png").write_bytes((images / "0.png").read_bytes())
    with pytest.raises(ValueError, match="Duplicate"):
        load_rows(labels, images, plan())


def test_human_annotation_aggregation_refuses_repeated_raters(tmp_path):
    source, target = tmp_path / "votes.csv", tmp_path / "means.csv"
    header = "image,subject_id,rater_id,rating,rights_id,cohort\n"
    rows = [f"a.png,p1,r{i},{i + 1},test,studio\n" for i in range(3)]
    source.write_text(header + "".join(rows))
    aggregate_annotations(source, target)
    result = list(csv.DictReader(target.open()))
    assert float(result[0]["rating"]) == 2 and int(result[0]["rating_count"]) == 3
    source.write_text(header + "".join(rows) + rows[0])
    with pytest.raises(ValueError, match="repeated"):
        aggregate_annotations(source, tmp_path / "other.csv")
    assert hashlib.sha256(target.read_bytes()).hexdigest()
