"""Generated features only: checks the input-guard arithmetic, not real-image behaviour."""

import numpy as np
import pytest
from aevyra_contracts.native_preview import NativePreviewResult
from aevyra_inference.native import fit_head
from aevyra_inference.native_input import distance, profile, verdict
from pydantic import ValidationError


def head_and_features():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(60, 16))
    return fit_head(x, 4 + x[:, 0] * 0.3, 1.0, 7), x


def test_training_portraits_are_typical_and_far_inputs_are_outside():
    head, x = head_and_features()
    p = profile(head, x)
    assert p["outside_above"] > p["caution_above"] >= p["training_max"]
    assert all(verdict(d, p) == "typical" for d in distance(head, x))
    far = head.mean + 10 * head.scale
    assert verdict(float(distance(head, far[None, :])[0]), p) == "outside"
    middle = (p["caution_above"] + p["outside_above"]) / 2
    assert verdict(middle, p) == "unusual"
    assert verdict(float("nan"), p) == "outside"


def test_older_checkpoints_without_a_profile_are_unchecked():
    assert verdict(9.0, None) == "unchecked"
    assert verdict(9.0, {"statistic": "other"}) == "unchecked"
    head, x = head_and_features()
    with pytest.raises(ValueError):
        profile(head, x[:3])


def base(**changes):
    value = dict(
        predicted_rating=4.2,
        native_scale=[1, 7],
        manifest_sha256="a" * 64,
        encoder="fixture",
        collection="fixture",
        research_only=True,
        synthetic=False,
        consumer_enabled=False,
        release_failures=[],
        duration_ms=1.0,
        peak_rss_kib=1,
    )
    value.update(changes)
    return value


def test_contract_withholds_scores_exactly_for_outside_inputs():
    assert NativePreviewResult.model_validate(base()).input_check.verdict == "unchecked"
    outside = {"verdict": "outside", "distance": 4.0, "caution_above": 1.8, "outside_above": 2.8}
    assert (
        NativePreviewResult.model_validate(
            base(predicted_rating=None, input_check=outside)
        ).predicted_rating
        is None
    )
    with pytest.raises(ValidationError):
        NativePreviewResult.model_validate(base(input_check=outside))
    with pytest.raises(ValidationError):
        NativePreviewResult.model_validate(base(predicted_rating=None))
