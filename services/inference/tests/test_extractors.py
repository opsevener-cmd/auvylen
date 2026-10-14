"""Software correctness; these synthetic tests say nothing about facial accuracy."""

import hashlib
from pathlib import Path

import numpy as np
import pytest
from aevyra_inference.extractors import (
    BASELINE,
    MOBILENET,
    WEIGHT_FILE,
    WEIGHT_SHA256,
    HandcraftedExtractor,
    availability,
    create_extractor,
    manifest,
    verified_weights,
)
from aevyra_inference.preference import checkpoint_adapter, split_groups, train
from test_preference import picture


def test_baseline_adapter_is_compatible_and_pretrained_fails_closed(tmp_path):
    from aevyra_inference.preference import extract

    payload = picture(125)
    assert create_extractor(BASELINE, tmp_path).extract_batch([payload]) == [extract(payload)]
    with pytest.raises(ValueError, match="batch limit"):
        HandcraftedExtractor().extract_batch([payload] * 9)
    assert availability(BASELINE, tmp_path)[0]
    assert not availability(MOBILENET, tmp_path)[0]
    (tmp_path / WEIGHT_FILE).write_bytes(b"not pretrained weights")
    with pytest.raises(ValueError, match="unavailable"):
        verified_weights(tmp_path)
    with pytest.raises(ValueError, match="Unknown"):
        create_extractor("unreviewed", tmp_path)


def test_pretrained_checkpoint_records_immutable_representation_and_training_only_statistics():
    # Numerical embedding fixture, not an execution of MobileNet.
    groups = [str(i // 2) for i in range(20)]
    training, heldout = split_groups(groups, 42, 0.2)
    features = np.ones((20, 1024))
    features[heldout] = 999
    model, metrics, actual_train, actual_heldout = train(
        features.tolist(),
        [float(i % 10 + 1) for i in range(20)],
        groups,
        alpha=10,
        seed=42,
        validation_fraction=0.2,
        rating_min=1,
        rating_max=10,
        snapshot_sha256="a" * 64,
        check=lambda: None,
        extractor=MOBILENET,
    )
    assert actual_train == training and actual_heldout == heldout
    assert model.mean == [1] * 1024 and model.scale == [0.05] * 1024
    assert model.representation["weight_sha256"] == WEIGHT_SHA256
    assert metrics["mean_baseline_rmse"] >= metrics["mean_baseline_mae"]
    assert checkpoint_adapter.validate_json(model.model_dump_json()) == model
    forged = model.model_dump()
    forged["representation"]["weight_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="representation"):
        checkpoint_adapter.validate_python(forged)
    forged = model.model_dump()
    forged["coefficients"][0] = float("nan")
    with pytest.raises(ValueError):
        checkpoint_adapter.validate_python(forged)
    forged = model.model_dump()
    forged["extractor"] = BASELINE
    with pytest.raises(ValueError):
        checkpoint_adapter.validate_python(forged)


@pytest.mark.pretrained
def test_real_mobilenet_batch_single_determinism_and_changed_pixels(pretrained_root):
    extractor = create_extractor(MOBILENET, pretrained_root)
    payloads = [picture(value) for value in (20, 125, 240)]
    batch = np.array(extractor.extract_batch(payloads))
    singles = np.array([extractor.extract_batch([payload])[0] for payload in payloads])
    assert batch.shape == (3, 1024)
    np.testing.assert_allclose(batch, singles, atol=1e-5, rtol=1e-5)
    assert not np.allclose(batch[0], batch[-1])
    recreated = create_extractor(MOBILENET, pretrained_root)
    np.testing.assert_array_equal(
        singles, np.array([recreated.extract_batch([p])[0] for p in payloads])
    )
    assert (
        manifest(MOBILENET)["weight_sha256"]
        == hashlib.sha256((Path(pretrained_root) / WEIGHT_FILE).read_bytes()).hexdigest()
    )
    with pytest.raises(ValueError, match="batch limit"):
        extractor.extract_batch([payloads[0]] * 9)
    with pytest.raises(ValueError, match="Image size limit"):
        extractor.extract_batch([b"x" * (10 * 1024 * 1024 + 1)])
