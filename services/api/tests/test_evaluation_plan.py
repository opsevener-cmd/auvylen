"""The preparatory validator must reject unapproved personal-data import plans."""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

script = Path(__file__).resolve().parents[3] / "scripts/validate-face-evaluation-plan.py"
spec = importlib.util.spec_from_file_location("evaluation_plan", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_evaluation_plan_needs_explicit_retention_and_authorization():
    clock = datetime(2026, 10, 13, tzinfo=UTC)
    plan = {
        "dataset_name": "Synthetic authorization test only",
        "license_name": "Test terms",
        "source_url": "https://example.org/dataset",
        "license_evidence_url": "https://example.org/license",
        "license_reviewed_by": "test reviewer",
        "authorization_reference": "test approval reference",
        "authorized_by": "test owner",
        "retention_approved_by": "test owner",
        "adult_only_verified": True,
        "minimum_subject_age": 18,
        "all_subject_ids_present": True,
        "image_count": 500,
        "retention_days": 7,
        "delete_by": (clock + timedelta(days=6)).isoformat(),
        "storage_location": "temporary_cloud",
        "temporary_cloud_explicitly_authorized": True,
        "backup_location_and_deletion_plan": "No real images or backups in this test",
        "worker_cleanup_and_access_revocation_tested": True,
        "ratings_source": "owner_numerical_annotations",
        "split_seed": 42,
        "validation_fraction": 0.2,
        "regularization_alpha": 10,
    }
    assert module.validate(plan, clock) == []
    for field, value in (
        ("temporary_cloud_explicitly_authorized", False),
        ("authorized_by", ""),
        ("retention_approved_by", ""),
        ("image_count", 501),
        ("minimum_subject_age", 17),
        ("all_subject_ids_present", False),
        ("delete_by", clock.isoformat()),
        ("ratings_source", "github_predictions"),
    ):
        assert module.validate({**plan, field: value}, clock), field
