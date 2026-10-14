import hashlib
from io import BytesIO

import numpy as np
import pytest
from aevyra_inference.engine import EnginePolicyError, EngineRegistry
from aevyra_inference.preference import (
    DIMENSION,
    PersonalRatingEngine,
    RidgeCheckpoint,
    extract,
    split_groups,
    train,
)
from PIL import Image


def picture(value):
    output = BytesIO()
    Image.new("RGB", (80, 80), (value, 40, 50)).save(output, "PNG")
    return output.getvalue()


def test_real_regression_generalizes_to_unseen_values_and_roundtrips():
    values = list(range(20, 241, 20))
    features = [extract(picture(value)) for value in values]
    ratings = [1 + 9 * value / 255 for value in values]
    groups = [str(i) for i in range(len(values))]
    checkpoint, metrics, training, validation = train(
        features,
        ratings,
        groups,
        alpha=0.01,
        seed=42,
        validation_fraction=0.2,
        rating_min=1,
        rating_max=10,
        snapshot_sha256="a" * 64,
        check=lambda: None,
    )
    # Golden bytes and prediction measured from preserved commit b37d2b8.
    assert hashlib.sha256(checkpoint.model_dump_json().encode()).hexdigest() == (
        "3367c2b36f603972bd45c4089d1f3c10bf07eabdbdedd057cb808967a9d388e9"
    )
    assert metrics["validation_mae"] < 0.02
    assert metrics["validation_mae"] < metrics["mean_baseline_mae"]
    assert set(training).isdisjoint(validation)
    restored = RidgeCheckpoint.model_validate_json(checkpoint.model_dump_json())
    engine = PersonalRatingEngine(restored, "1")
    score = EngineRegistry([engine]).score(
        "custom", picture(125), production=True, purpose="research"
    )
    with pytest.raises(EnginePolicyError):
        EngineRegistry([engine]).score("custom", picture(125), production=True)
    assert score.raw_score == 5.411773755501414
    assert score.synthetic is False
    assert abs(score.raw_score - (1 + 9 * 125 / 255)) < 0.02
    assert len(extract(picture(125))) == DIMENSION
    # The fitted model changes when labels change; outputs are not hashes/mock scores.
    reversed_model, *_ = train(
        features,
        [11 - score for score in ratings],
        groups,
        alpha=0.01,
        seed=42,
        validation_fraction=0.2,
        rating_min=1,
        rating_max=10,
        snapshot_sha256="b" * 64,
        check=lambda: None,
    )
    assert (
        PersonalRatingEngine(reversed_model, "2").predict(picture(220))
        < engine.predict(picture(220)) - 4
    )


def test_person_group_split_and_train_only_preprocessing():
    groups = [str(i // 2) for i in range(12)]
    training, validation = split_groups(groups, 4, 0.3)
    assert {groups[i] for i in training}.isdisjoint({groups[i] for i in validation})
    assert split_groups(groups, 4, 0.3) == (training, validation)
    features = np.ones((12, DIMENSION))
    features[validation] = 1000  # A holdout distribution must not influence fitted preprocessing.
    ratings = list(range(12))
    checkpoint, *_ = train(
        features.tolist(),
        ratings,
        groups,
        alpha=1,
        seed=4,
        validation_fraction=0.3,
        rating_min=0,
        rating_max=12,
        snapshot_sha256="a" * 64,
        check=lambda: None,
    )
    assert checkpoint.mean == [1] * DIMENSION
    assert checkpoint.scale == [0.05] * DIMENSION


def test_invalid_training_and_checkpoint_rejected():
    with pytest.raises(ValueError):
        split_groups(["same-person"] * 10, 42, 0.2)
    with pytest.raises(ValueError):
        train(
            [[float("nan")] * DIMENSION] * 10,
            list(range(10)),
            [str(i) for i in range(10)],
            alpha=1,
            seed=42,
            validation_fraction=0.2,
            rating_min=0,
            rating_max=10,
            snapshot_sha256="a" * 64,
            check=lambda: None,
        )
