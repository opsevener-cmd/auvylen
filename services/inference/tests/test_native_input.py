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
    assert NativePreviewResult.model_validate(base(predicted_rating=None)).predicted_rating is None


@pytest.mark.parametrize(
    "patch",
    [
        {"caution_above": -1},
        {"outside_above": 1},
        {"outside_above": float("nan")},
        {"outside_above": float("inf")},
        {"caution_above": True},
        {"outside_above": None},
    ],
)
def test_malformed_known_profiles_never_fall_back_to_unchecked(patch):
    from aevyra_inference.native_input import STATISTIC

    config = {"statistic": STATISTIC, "caution_above": 1.8, "outside_above": 2.8, **patch}
    with pytest.raises(ValueError):
        verdict(1.0, config)


def test_checked_contract_rejects_disagreeing_verdict_and_distance():
    for check in [
        {"verdict": "typical", "distance": 4, "caution_above": 1.8, "outside_above": 2.8},
        {"verdict": "unusual", "distance": 1, "caution_above": 1.8, "outside_above": 2.8},
        {"verdict": "typical"},
    ]:
        with pytest.raises(ValidationError):
            NativePreviewResult.model_validate(base(input_check=check))


def test_prediction_withholds_without_supported_profile(monkeypatch, tmp_path):
    """Generated feature arithmetic and mocked provenance, not human-trained inference evidence."""
    from types import SimpleNamespace

    from aevyra_inference import native_preview as preview

    head, x = head_and_features()
    item = SimpleNamespace(
        report={}, encoder="generated-fixture", collection=SimpleNamespace(name="fixture")
    )
    monkeypatch.setattr(preview, "reviewed_checkpoint", lambda *_: (head, item))
    monkeypatch.setattr(
        preview, "create_extractor", lambda *_: SimpleNamespace(extract_batch=lambda _: x[:1])
    )
    monkeypatch.setattr(preview, "release_failures", lambda _: ["generated_test_only"])
    result = preview.predict(tmp_path, "a" * 64, tmp_path, b"generated-feature-fixture-not-photo")
    assert result["input_check"]["verdict"] == "unchecked"
    assert result["predicted_rating"] is None


def test_experiment_undefined_ranks_are_null_not_zero(monkeypatch, tmp_path):
    """Constant protocol fixtures test report handling, not aesthetic prediction quality."""
    from types import SimpleNamespace

    from aevyra_inference import native_experiments as experiment

    subjects = [f"generated-subject-{i}" for i in range(10)]
    monkeypatch.setattr(experiment, "development_table", lambda *_: {})
    monkeypatch.setattr(
        experiment,
        "load_rows",
        lambda *_: ([b"generated"] * 10, subjects, np.linspace(2, 6, 10), [], "fixture"),
    )
    monkeypatch.setattr(
        experiment,
        "encode",
        lambda *_: {key: np.zeros((10, 2)) for key in ("clean", "mirror", "lighting", "crop")},
    )
    protocol = lambda *_: (SimpleNamespace(predict=lambda x: np.full(len(x), 4.0)), 1.0)  # noqa: E731
    monkeypatch.setattr(experiment, "protocol_a", protocol)
    monkeypatch.setattr(experiment, "protocol_b", protocol)
    report = experiment.study(
        tmp_path, tmp_path, SimpleNamespace(rating_max=7), tmp_path, outer_repeats=1, draws=10
    )
    assert report["variants"]["mobilenet-A"]["spearman"] is None
    assert report["variants"]["mobilenet-A"]["repeat_averaged_spearman"] is None
