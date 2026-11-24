"""Development-only datasets for Phase 7B. The sealed London subjects never leave this module.

``london`` fetches the authors' pinned commits onto the local (ephemeral) disk, verifies
the source hashes with the repository's own importer, removes the 20 sealed seed-42
subjects before any rating is parsed, deletes their portraits from disk, and returns
development records only. Raw portraits and ratings are never written to the store.

``synthetic`` returns generated pictures and generated ratings for pipeline smoke tests.
It is flagged ``synthetic=True`` everywhere and must never be compared with real results.

Every real source passes the release gate's own rights checks (``rights_failures`` in
``aevyra_inference.aesthetic_checkpoint``) before anything is fetched: restricted datasets
(SCUT-FBP5500, MEBeauty, the Chicago Face Database), non-commercial or research-only
licences, missing subject consent and undocumented adult age are refused. The only check
not required here is commercial-use permission. That is a release question, and London's
stays False so nothing built from it can pass the release gate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

IMAGES_COMMIT = "fa8b78fda2d659bb74ce62fcd99c4407551d2a77"
RATINGS_COMMIT = "1b5d2a179edd873162a54dec11faff2163afe6c0"
SOURCES = {
    "images": "https://github.com/debruine/webmorphR.stim",
    "ratings": "https://github.com/debruine/demopsydata",
}
# Release-gate rights checks that research admission does not require (see module docstring).
RESEARCH_NOT_REQUIRED = frozenset({"commercial_use_not_permitted"})


@dataclass(frozen=True)
class SourceRights:
    """Operator-recorded rights evidence for a real source; nothing is inferred from images."""

    name: str
    license: str
    terms_url: str
    subject_consent_reference: str | None
    # "documented" only when every subject's age comes from source metadata (never appearance).
    adult_age_verification: str | None
    commercial_use_permitted: bool = False
    synthetic: bool = False


LONDON_RIGHTS = SourceRights(
    name="Face Research Lab London Set, neutral frontal (development subjects)",
    license="Portraits CC BY 4.0 (DeBruine & Jones 2017); ratings MIT + LICENCE (demopsydata)",
    terms_url=f"{SOURCES['images']}/blob/{IMAGES_COMMIT}/LICENSE.md",
    subject_consent_reference=(
        f"webmorphR.stim@{IMAGES_COMMIT[:8]} README: signed consent for lab- and web-based "
        "studies; research/phase7b/README.md section 1"
    ),
    # native_london.prepare keeps only subjects whose author-reported face_age is 18-120 and
    # checks the fixed adult subject registry hash.
    adult_age_verification="documented",
    # Consumer-service and publicity rights are not established: research only.
    commercial_use_permitted=False,
)


def admit(rights: SourceRights) -> None:
    """Refuse a source that fails the release gate's rights rules (research subset)."""
    from aevyra_inference.aesthetic_checkpoint import rights_failures

    failures = [f for f in rights_failures(rights) if f not in RESEARCH_NOT_REQUIRED]
    if failures:
        raise ValueError(f"Dataset refused by the release-gate rights rules: {failures}")


@dataclass(frozen=True)
class Item:
    image: str  # stable name, e.g. 001_03.jpg
    subject: str
    sha256: str
    rating: float  # mean of adult raters, native 1-7
    histogram: tuple[float, ...]  # share of adult raters choosing 1..7
    raters: int
    path: Path = field(compare=False)

    def payload(self) -> bytes:
        return self.path.read_bytes()


@dataclass(frozen=True)
class Dataset:
    name: str
    synthetic: bool
    items: list[Item]
    provenance: dict[str, object]

    @property
    def fingerprint(self) -> str:
        rows = [(i.image, i.subject, i.sha256, round(i.rating, 9)) for i in self.items]
        return hashlib.sha256(repr(rows).encode()).hexdigest()


def _git_file(repo: Path, commit: str, path: str, destination: Path) -> None:
    content = subprocess.run(
        ["git", "-C", str(repo), "show", f"{commit}:{path}"], check=True, capture_output=True
    ).stdout
    destination.write_bytes(content)
    destination.chmod(0o600)


def london(workdir: Path) -> Dataset:
    admit(LONDON_RIGHTS)  # Before anything is cloned or read.
    from aevyra_inference.native_dev_study import HOLDOUT_SEED, development_table
    from aevyra_inference.native_london import prepare

    workdir = Path(workdir)
    root, clones = workdir / "london", workdir / "clones"
    if root.exists():
        shutil.rmtree(root)
    clones.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(parents=True, mode=0o700)
    for name, url in SOURCES.items():
        if not (clones / name).exists():
            subprocess.run(
                [
                    "git",
                    "clone",
                    "-q",
                    "--filter=blob:none",
                    "--no-checkout",
                    url,
                    str(clones / name),
                ],
                check=True,
            )
    listing = subprocess.run(
        [
            "git",
            "-C",
            str(clones / "images"),
            "ls-tree",
            "--name-only",
            IMAGES_COMMIT,
            "inst/neutral_front/",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    for path in listing:
        stem = Path(path).name
        if len(stem) == 10 and stem.endswith("_03.jpg") and stem[:3].isdigit():
            _git_file(clones / "images", IMAGES_COMMIT, path, root / "images" / stem)
    _git_file(
        clones / "ratings",
        RATINGS_COMMIT,
        "inst/extdata/london_faces_info.csv",
        root / "source-info.csv",
    )
    _git_file(
        clones / "ratings",
        RATINGS_COMMIT,
        "inst/extdata/london_faces_ratings.csv",
        root / "source-ratings.csv",
    )
    prepared = prepare(root)  # Verifies pinned source and inventory hashes; refuses changes.
    development = root / "development.csv"
    sizes = development_table(root / "means.csv", HOLDOUT_SEED, development)
    rows = list(csv.DictReader(development.open(newline="")))
    keep = {row["image"] for row in rows}
    for image in (root / "images").iterdir():
        if image.name not in keep:
            image.unlink()  # Sealed (and ineligible) portraits never stay on disk.
    with (root / "source-ratings.csv").open(newline="") as file:
        raters = [
            r
            for r in csv.DictReader(file)
            if r["rater_age"] not in ("", "NA") and 18 <= float(r["rater_age"]) <= 120
        ]
    items = []
    for row in rows:
        column = "X" + row["image"].split("_")[0]
        votes = np.asarray([float(r[column]) for r in raters if r[column] not in ("", "NA")])
        counts = np.asarray([(votes == k).sum() for k in range(1, 8)], dtype=float)
        path = root / "images" / row["image"]
        items.append(
            Item(
                image=row["image"],
                subject=row["subject_id"],
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                rating=float(row["rating"]),
                histogram=tuple(counts / counts.sum()),
                raters=int(counts.sum()),
                path=path,
            )
        )
    for item in items:
        if abs(float(np.dot(item.histogram, np.arange(1, 8))) - item.rating) > 1e-6:
            raise ValueError("Histogram and prepared mean disagree")
    (root / "source-ratings.csv").unlink()  # Only development aggregates remain in memory.
    return Dataset(
        name="london-development",
        synthetic=False,
        items=items,
        provenance={
            "images_commit": IMAGES_COMMIT,
            "ratings_commit": RATINGS_COMMIT,
            "inventory_sha256": prepared.get("selected_image_inventory_sha256"),
            **sizes,
            "licences": LONDON_RIGHTS.license,
            "rights_checks": "release-gate rights_failures; commercial use not permitted",
        },
    )


def synthetic(workdir: Path, subjects: int = 48, seed: int = 0) -> Dataset:
    """Generated pictures with generated ratings tied to a colour feature. Pipeline test only."""
    rng = np.random.default_rng(seed)
    folder = Path(workdir) / "synthetic"
    folder.mkdir(parents=True, exist_ok=True)
    items = []
    for n in range(subjects):
        tone = rng.uniform(0, 1)
        pixels = np.clip(rng.normal(80 + 120 * tone, 25, (256, 224, 3)), 0, 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(pixels).save(buffer, "PNG")
        path = folder / f"{n:03d}_03.png"
        path.write_bytes(buffer.getvalue())
        logits = -((np.arange(1, 8) - (2 + 4 * tone)) ** 2) / 2
        histogram = np.exp(logits) / np.exp(logits).sum()
        items.append(
            Item(
                image=path.name,
                subject=f"gen{n:03d}",
                sha256=hashlib.sha256(buffer.getvalue()).hexdigest(),
                rating=float(np.dot(histogram, np.arange(1, 8))),
                histogram=tuple(histogram),
                raters=0,
                path=path,
            )
        )
    return Dataset(
        "synthetic-smoke", True, items, {"generator": "auvylen7b.data.synthetic", "seed": seed}
    )
