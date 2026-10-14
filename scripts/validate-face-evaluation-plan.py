"""Validate an operator's evaluation plan. Does not import images or confer authorization."""

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse


def validate(plan: dict, clock: datetime) -> list[str]:
    errors = []
    for field in (
        "dataset_name",
        "license_name",
        "license_reviewed_by",
        "authorization_reference",
        "authorized_by",
        "retention_approved_by",
        "backup_location_and_deletion_plan",
    ):
        if (
            not isinstance(plan.get(field), str)
            or not plan[field].strip()
            or plan[field] == "UNREVIEWED"
        ):
            errors.append(f"Missing reviewed evidence: {field}")
    for field in ("source_url", "license_evidence_url"):
        parsed = urlparse(str(plan.get(field, "")))
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.endswith(".invalid"):
            errors.append(f"Provide an actual evidence URL: {field}")
    for field in (
        "adult_only_verified",
        "all_subject_ids_present",
        "worker_cleanup_and_access_revocation_tested",
    ):
        if plan.get(field) is not True:
            errors.append(f"Required confirmation: {field}")
    if type(plan.get("minimum_subject_age")) is not int or plan["minimum_subject_age"] < 18:
        errors.append("Every subject must be verified adult (18+)")
    if type(plan.get("image_count")) is not int or not 8 <= plan["image_count"] <= 500:
        errors.append("Image count must be 8–500; production quota unchanged")
    days = plan.get("retention_days")
    if type(days) is not int or not 1 <= days <= 90:
        errors.append("Retention must be 1–90 days")
    else:
        try:
            expiry = datetime.fromisoformat(plan.get("delete_by", "").replace("Z", "+00:00"))
            if expiry.tzinfo is None or not clock < expiry <= clock + timedelta(days=days):
                errors.append(
                    "Deletion deadline must be future, timezone-aware and within retention"
                )
        except (ValueError, TypeError):
            errors.append("Invalid deletion deadline")
    if plan.get("storage_location") not in {"temporary_cloud", "approved_persistent_private_host"}:
        errors.append("Specify an approved private storage location")
    if (
        plan.get("storage_location") == "temporary_cloud"
        and plan.get("temporary_cloud_explicitly_authorized") is not True
    ):
        errors.append("Temporary cloud storage requires explicit user authorization")
    if plan.get("ratings_source") != "owner_numerical_annotations":
        errors.append("Use personal annotations, never external-model scores")
    if (
        plan.get("split_seed"),
        plan.get("validation_fraction"),
        plan.get("regularization_alpha"),
    ) != (42, 0.2, 10):
        errors.append(
            "This preregistered protocol uses seed 42, validation fraction 0.2 and alpha 10"
        )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    args = parser.parse_args()
    with open(args.plan, "rb") as file:
        raw = file.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise SystemExit("Plan size limit")
    plan = json.loads(raw)
    errors = validate(plan, datetime.now(UTC))
    if errors:
        print("Plan rejected:\n- " + "\n- ".join(errors))
        raise SystemExit(1)
    print("Plan fields validated; retain independent authorization evidence before any import.")
    print("Plan SHA-256:", hashlib.sha256(raw).hexdigest())
    print("No images were read, downloaded, imported or persisted.")


if __name__ == "__main__":
    main()
