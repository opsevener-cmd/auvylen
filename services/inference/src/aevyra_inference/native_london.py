"""Prepare the authors' London Set for a private human-rated feasibility experiment.

No network requests: acquire the pinned author files as described in the protocol first.
This importer never uses private account data or turns model outputs into labels.
"""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from aevyra_inference.native_data import Collection, Rights

STIM_REVISION = "fa8b78fda2d659bb74ce62fcd99c4407551d2a77"
RATINGS_REVISION = "1b5d2a179edd873162a54dec11faff2163afe6c0"
DOI = "https://doi.org/10.6084/m9.figshare.5047666.v5"
SOURCE_HASHES = {
    "source-info.csv": "c5cadd839e18c9c480dceffcadf31afaa374ab58cb60f7a7b5ff4612e9a22903",
    "source-ratings.csv": "eadc7a6710b752fb9ca537f84feb420636a1603d1a02dee3d178898f80d35195",
}
INVENTORY_SHA256 = "fe0a985e5c4f1209e43ee90dba74fae931a94e3da34fc4d668389ef4e609df8d"


def number(value: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return float("nan")


def prepare(root: Path) -> dict[str, Any]:
    for name, digest in SOURCE_HASHES.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Pinned author source file integrity failure")
    with (root / "source-info.csv").open(newline="") as f:
        info = list(csv.DictReader(f))
    with (root / "source-ratings.csv").open(newline="") as f:
        raters = list(csv.DictReader(f))
    adults = [r for r in raters if 18 <= number(r["rater_age"]) <= 120]
    if len(info) != 102 or len(raters) != 2513 or not adults:
        raise ValueError("Unexpected official dataset shape")
    rows: list[tuple[str, str, float, int, str, str]] = []
    metadata, hashes, standard_errors = {}, {}, []
    for item in info:
        age = number(item["face_age"])
        if not math.isfinite(age) or not 18 <= age <= 120:
            continue
        subject = f"{int(item['face_id'].removeprefix('X')):03}"
        image = root / "images" / f"{subject}_03.jpg"
        if image.is_symlink() or not image.is_file():
            raise ValueError("Missing official neutral portrait")
        votes = np.asarray([number(r.get("X" + subject, "")) for r in adults])
        votes = votes[np.isfinite(votes)]
        if len(votes) < 3 or np.any((votes < 1) | (votes > 7)):
            raise ValueError("Invalid real human rating columns")
        rows.append(
            (image.name, subject, float(votes.mean()), len(votes), "london-ccby4", item["face_sex"])
        )
        metadata[subject] = {
            "sex": item["face_sex"],
            "ethnicity": item["face_eth"],
            "age_band": "18–29" if age < 30 else "30+",
        }
        hashes[image.name] = hashlib.sha256(image.read_bytes()).hexdigest()
        standard_errors.append(float(votes.std(ddof=1) / np.sqrt(len(votes))))
    if len(rows) != 100:
        raise ValueError("Unexpected adult reported-age subset")
    if hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest() != INVENTORY_SHA256:
        raise ValueError("Pinned neutral portrait inventory mismatch")
    plan = Collection(
        name="London Set: reported-age adults, neutral frontal; feasibility only",
        rating_max=7,
        synthetic=False,
        encoder_rights_review="docs/pretrained-representation.md; research only",
        annotator_population=(
            f"{len(adults)} original author-provided rater records "
            "aged >=18; missing ratings omitted"
        ),
        rating_protocol_reference=DOI + "; original 1–7 relative-to-average anchors; no conversion",
        rights={
            "london-ccby4": Rights(
                image_license="CC BY 4.0; author neutral-set README and " + DOI,
                annotation_license=(
                    "CC BY 4.0 original London ratings release; authors' faceatt attribution"
                ),
                subject_release=(
                    "Authors report signed adult subject consent for lab/web-based research"
                ),
                training_permission=(
                    "CC BY copying/adaptation; published consent scope: private research pilot"
                ),
                derived_weight_permission=(
                    "Internal research adaptation; no public weight or "
                    "commercial-service clearance claimed"
                ),
                reviewer=(
                    "Auvylen source audit 2026-11-01; primary author records and CC BY legal code"
                ),
                adult_confirmed=True,
                research_allowed=True,
                commercial_allowed=False,
            )
        },
    )
    for path, text in [
        (root / "collection.json", plan.model_dump_json(indent=2)),
        (root / "subject-metadata.json", json.dumps(metadata)),
        (root / "image-hashes.json", json.dumps(hashes, indent=2)),
    ]:
        with path.open("x") as f:
            path.chmod(0o600)
            f.write(text + "\n")
    with (root / "means.csv").open("x", newline="") as f:
        (root / "means.csv").chmod(0o600)
        w = csv.writer(f)
        w.writerow(["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"])
        w.writerows(rows)
    summary = {
        "source_subjects": len(info),
        "eligible_subjects": len(rows),
        "excluded_missing_subject_age": len(info) - len(rows),
        "source_rater_records": len(raters),
        "eligible_adult_rater_records": len(adults),
        "human_ratings_used": sum(r[3] for r in rows),
        "native_scale": [1, 7],
        "ratings_per_photo_min": min(r[3] for r in rows),
        "ratings_per_photo_max": max(r[3] for r in rows),
        "label_mean_se_median": float(np.median(standard_errors)),
        "sources": {"images_commit": STIM_REVISION, "ratings_commit": RATINGS_REVISION, "doi": DOI},
        "source_info_sha256": hashlib.sha256((root / "source-info.csv").read_bytes()).hexdigest(),
        "source_ratings_sha256": hashlib.sha256(
            (root / "source-ratings.csv").read_bytes()
        ).hexdigest(),
        "selected_image_inventory_sha256": hashlib.sha256(
            json.dumps(hashes, sort_keys=True).encode()
        ).hexdigest(),
    }
    return summary


def validated_metadata(root: Path) -> dict[str, dict[str, str]]:
    """Rebuild declared cohort metadata from the pinned author CSV before reporting."""
    if (
        hashlib.sha256((root / "source-info.csv").read_bytes()).hexdigest()
        != SOURCE_HASHES["source-info.csv"]
    ):
        raise ValueError("Author metadata integrity failure")
    with (root / "source-info.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    expected = {
        f"{int(r['face_id'].removeprefix('X')):03}": {
            "sex": r["face_sex"],
            "ethnicity": r["face_eth"],
            "age_band": "18–29" if number(r["face_age"]) < 30 else "30+",
        }
        for r in rows
        if 18 <= number(r["face_age"]) <= 120
    }
    actual: dict[str, dict[str, str]] = json.loads((root / "subject-metadata.json").read_text())
    if actual != expected:
        raise ValueError("Derived subgroup metadata differs from author records")
    return actual


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root), indent=2))
