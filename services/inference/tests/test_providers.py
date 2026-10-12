from uuid import uuid4

import pytest
from aevyra_inference.custom import DatasetSnapshot, PairwisePreference, Rating
from aevyra_inference.providers import PROVIDERS, ProviderCatalog


def test_every_optional_provider_is_honestly_unavailable_without_installation(tmp_path):
    catalog = ProviderCatalog(list(PROVIDERS), tmp_path)
    assert len(catalog.statuses()) == 5
    assert all(not status.available for status in catalog.statuses() if status.slug != "custom")
    for slug in PROVIDERS:
        with pytest.raises(RuntimeError, match="unavailable"):
            catalog.load(slug)
    assert ProviderCatalog(["custom"], tmp_path).status("custom") == catalog.status("custom")


def test_custom_annotation_contracts():
    left, right, owner = uuid4(), uuid4(), uuid4()
    DatasetSnapshot(
        dataset_id=uuid4(),
        owner_id=owner,
        version=1,
        image_artifact_ids=[left, right],
        consent_reference="operator-consent",
    )
    Rating(image_artifact_id=left, rating=7, annotator_id=owner)
    PairwisePreference(
        left_artifact_id=left,
        right_artifact_id=right,
        preferred_artifact_id=left,
        annotator_id=owner,
    )
    with pytest.raises(ValueError):
        PairwisePreference(
            left_artifact_id=left,
            right_artifact_id=left,
            preferred_artifact_id=left,
            annotator_id=owner,
        )
    with pytest.raises(ValueError):
        Rating(image_artifact_id=left, rating=float("nan"), annotator_id=owner)
