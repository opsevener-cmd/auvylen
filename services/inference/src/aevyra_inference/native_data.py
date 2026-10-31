"""Private annotation ingestion and deterministic, train-only photographic perturbations."""

import csv
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from pydantic import BaseModel, ConfigDict, Field


class Rights(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    image_license: str = Field(min_length=1)
    annotation_license: str = Field(min_length=1)
    subject_release: str = Field(min_length=1)
    training_permission: str = Field(min_length=1)
    derived_weight_permission: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    adult_confirmed: Literal[True]
    research_allowed: Literal[True]
    commercial_allowed: bool = False


class Collection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    name: str = Field(min_length=1)
    rights: dict[str, Rights] = Field(min_length=1)
    synthetic: bool = False
    encoder_rights_review: str = Field(min_length=1)
    annotator_population: str = Field(min_length=1)
    rating_protocol_reference: str = Field(min_length=1)


def load_rows(
    csv_path: Path, image_root: Path, plan: Collection
) -> tuple[list[bytes], list[str], np.ndarray, list[str], str]:
    root = image_root.resolve()
    seen: set[str] = set()
    payloads: list[bytes] = []
    subjects: list[str] = []
    scores: list[float] = []
    cohorts: list[str] = []
    expected = ["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"]
    with csv_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != expected:
            raise ValueError("Expected image,subject_id,rating,rating_count,rights_id,cohort")
        for row in reader:
            if len(payloads) >= 3000:
                raise ValueError("Initial CPU training limit is 3000 images")
            relative = Path(row["image"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Image path must be relative")
            source = root / relative
            if source.is_symlink() or not source.resolve().is_relative_to(root):
                raise ValueError("Image path escapes collection")
            if row["rights_id"] not in plan.rights:
                raise ValueError("Image/annotation rights reference missing")
            subject = row["subject_id"].strip()
            if not subject or len(subject) > 200:
                raise ValueError("Stable pseudonymous subject required")
            rating, count = float(row["rating"]), int(row["rating_count"])
            if not np.isfinite(rating) or not 1 <= rating <= 5 or count < 3:
                raise ValueError(
                    "Native mean rating 1–5 and >=3 independent human ratings required"
                )
            if source.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Training image exceeds byte limit")
            if sum(map(len, payloads)) + source.stat().st_size > 256 * 1024 * 1024:
                raise ValueError("Collection exceeds initial 256-MiB in-memory budget")
            raw = source.read_bytes()
            with Image.open(BytesIO(raw), formats=["JPEG", "PNG"]) as image:
                if (
                    max(image.size) > 4096
                    or min(image.size) < 224
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError("Use a single bounded portrait >=224px")
                rgb = ImageOps.exif_transpose(image).convert("RGB")
                digest = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
            if digest in seen:
                raise ValueError("Duplicate decoded image; resolve subject/near-duplicate leakage")
            seen.add(digest)
            payloads.append(raw)
            subjects.append(subject)
            scores.append(rating)
            cohorts.append(row["cohort"].strip() or "unspecified")
    if not payloads:
        raise ValueError("No authorized labels supplied")
    # Stable collection digest binds pixels and labels/rights, independent of row filenames.
    digest = hashlib.sha256(csv_path.read_bytes() + "".join(sorted(seen)).encode()).hexdigest()
    return payloads, subjects, np.asarray(scores, dtype=np.float64), cohorts, digest


def perturb(payload: bytes, kind: str) -> bytes:
    with Image.open(BytesIO(payload)) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        if kind == "lighting":
            rgb = ImageEnhance.Brightness(rgb).enhance(0.85)
        elif kind == "crop":
            w, h = rgb.size
            rgb = rgb.crop((round(w * 0.05), round(h * 0.05), round(w * 0.95), round(h * 0.95)))
        elif kind == "rotation":
            rgb = rgb.rotate(5, resample=Image.Resampling.BICUBIC)
        else:
            raise ValueError("Unknown photographic perturbation")
        out = BytesIO()
        rgb.info.clear()
        rgb.save(out, "PNG")
        return out.getvalue()


def aggregate_annotations(source: Path, target: Path) -> None:
    """Human mean/count only. Refuse duplicate rater/image votes and inconsistent grouping."""
    groups: dict[str, tuple[tuple[str, str, str], dict[str, float]]] = {}
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != [
            "image",
            "subject_id",
            "rater_id",
            "rating",
            "rights_id",
            "cohort",
        ]:
            raise ValueError("Invalid raw annotation columns")
        for index, row in enumerate(reader):
            if index >= 100000 or len(groups) > 3000:
                raise ValueError("Initial annotation collection limit exceeded")
            key, rater = row["image"], row["rater_id"].strip()
            if not rater:
                raise ValueError("Pseudonymous rater required")
            metadata = (row["subject_id"], row["rights_id"], row["cohort"])
            if key not in groups:
                groups[key] = (metadata, {})
            stored, ratings = groups[key]
            if stored != metadata or rater in ratings:
                raise ValueError("Conflicting subject/rights or repeated rater")
            value = float(row["rating"])
            if not np.isfinite(value) or not 1 <= value <= 5:
                raise ValueError("Human ratings must use native scale 1–5")
            ratings[rater] = value
    if not groups or any(len(ratings) < 3 for _, ratings in groups.values()):
        raise ValueError("Every portrait requires >=3 independent human ratings")
    with target.open("x", newline="", encoding="utf-8") as f:
        import os

        os.chmod(target, 0o600)
        writer = csv.writer(f)
        writer.writerow(["image", "subject_id", "rating", "rating_count", "rights_id", "cohort"])
        for image, (metadata, ratings) in sorted(groups.items()):
            subject, rights, cohort = metadata
            writer.writerow(
                [
                    image,
                    subject,
                    float(np.mean(list(ratings.values()))),
                    len(ratings),
                    rights,
                    cohort,
                ]
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Aggregate authorized human annotations; no pseudo-labels"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    aggregate_annotations(args.source, args.target)
