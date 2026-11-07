"""Compatibility/statistical controls, not fabricated facial aesthetic experiments."""

import hashlib
import json

import numpy as np
import pytest
from aevyra_inference.native import fit_head
from aevyra_inference.native_checkpoint import load, new_manifest, write
from aevyra_inference.native_london import number, prepare
from aevyra_inference.native_uncertainty import uncertainty
from pydantic import ValidationError
from test_native import plan


def test_native_seven_preserves_high_ratings_and_checkpoint_scale(tmp_path):
    rng = np.random.default_rng(8)
    x = rng.normal(size=(50, 230))
    y = 6.0 + 0.1 * x[:, 0]
    head = fit_head(x, y, 1.0, rating_max=7)
    assert head.predict(x).mean() > 5
    collection = plan().model_copy(update={"rating_max": 7})
    item = new_manifest("rgb-grid-texture-v1", collection, "0" * 64, head, {})
    root = tmp_path / "seven"
    pin = write(root, head, item)
    restored, manifest = load(root, pin, require_release=False)
    assert manifest.native_scale == (1, 7)
    assert np.array_equal(restored.predict(x), head.predict(x))
    with pytest.raises(ValidationError):
        type(item).model_validate({**item.model_dump(), "format": "auvylen-native-ridge-v1"})
    with pytest.raises(ValueError):
        write(tmp_path / "bad", fit_head(x, y, 1.0), item)


def test_legacy_five_manifest_without_new_scale_field_still_loads(tmp_path):
    x = np.arange(60 * 230, dtype=float).reshape(60, 230)
    y = np.linspace(2, 4, 60)
    head = fit_head(x, y, 1.0)
    item = new_manifest("rgb-grid-texture-v1", plan(), "0" * 64, head, {})
    root = tmp_path / "legacy"
    write(root, head, item)
    raw = item.model_dump(mode="json")
    raw["format"] = "auvylen-native-ridge-v1"
    del raw["collection"]["rating_max"]
    data = json.dumps(raw).encode()
    (root / "manifest.json").write_bytes(data)
    restored, manifest = load(root, hashlib.sha256(data).hexdigest(), require_release=False)
    assert manifest.native_scale == (1, 5)
    assert np.array_equal(head.predict(x), restored.predict(x))


def test_bootstrap_control_and_invalid_inputs():
    target = np.linspace(1, 7, 20)
    subjects = [str(i) for i in range(20)]
    result = uncertainty(target, target, subjects, np.ones(20) * 4, draws=100)
    assert result["intervals"]["mae"]["low"] == 0
    assert result["intervals"]["mae"]["high"] == 0
    assert result["intervals"]["paired_mean_baseline_delta_mae"]["high"] < 0
    assert result == uncertainty(target, target, subjects, np.ones(20) * 4, draws=100)
    with pytest.raises(ValueError):
        uncertainty(target, target, ["same"] * 20, target, draws=100)
    with pytest.raises(ValueError):
        uncertainty(np.full(20, np.nan), target, subjects, target, draws=100)


def test_source_pins_refuse_relabelled_dataset(tmp_path):
    (tmp_path / "source-info.csv").write_text("not the author data")
    with pytest.raises(ValueError, match="integrity"):
        prepare(tmp_path)
    assert np.isnan(number("NA"))
    assert number("18") == 18


def test_seven_point_raw_annotations_are_not_rescaled(tmp_path):
    from aevyra_inference.native_data import aggregate_annotations

    source = tmp_path / "votes.csv"
    target = tmp_path / "means.csv"
    source.write_text(
        "image,subject_id,rater_id,rating,rights_id,cohort\n"
        "a.jpg,p,a,6,r,c\na.jpg,p,b,6,r,c\na.jpg,p,c,6,r,c\n"
    )
    aggregate_annotations(source, target, rating_max=7)
    import csv

    with target.open() as f:
        row = next(csv.DictReader(f))
    assert float(row["rating"]) == 6
    with pytest.raises(ValueError):
        aggregate_annotations(source, tmp_path / "invalid.csv", rating_max=5)


def test_absent_test_cohorts_are_reported_with_zero_counts():
    from aevyra_inference.native_london_evaluate import subgroup_counts

    metadata = {
        "a": {"sex": "f", "ethnicity": "x", "age_band": "young"},
        "b": {"sex": "m", "ethnicity": "y", "age_band": "older"},
    }
    counts = subgroup_counts(metadata, ["a", "b"], {"train": [0], "validation": [], "test": [1]})
    assert counts["ethnicity"]["x"]["test"] == 0
    assert counts["ethnicity"]["y"]["train"] == 0
    assert counts["sex"]["f"]["train"] == 1
