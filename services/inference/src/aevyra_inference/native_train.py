"""Offline first-generation population model. Native labels only; no pseudo-labels."""

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable
from itertools import batched
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aevyra_inference.aesthetic import split_by_subject
from aevyra_inference.extractors import (
    BASELINE,
    BATCH_SIZE,
    MOBILENET,
    FeatureExtractor,
    create_extractor,
)
from aevyra_inference.native import NativeHead, metrics, select_model
from aevyra_inference.native_checkpoint import Manifest, new_manifest, release_failures, write
from aevyra_inference.native_data import Collection, load_rows, perturb


def features(payloads: Iterable[bytes], extractor: FeatureExtractor) -> NDArray[np.float64]:
    values = []
    for batch in batched(payloads, BATCH_SIZE):
        values.extend(extractor.extract_batch(batch))
    return np.asarray(values, dtype=np.float64)


def run(
    labels: Path,
    images: Path,
    plan: Collection,
    encoder_root: Path,
    *,
    seed: int = 42,
    encoders: tuple[str, ...] = (BASELINE, MOBILENET),
    pose_review: str = "",
) -> tuple[NativeHead, Manifest]:
    payloads, subjects, y, cohorts, digest = load_rows(labels, images, plan)
    train, _, test = split_by_subject(subjects, seed)
    matrices, views = {}, {}
    extractors = {name: create_extractor(name, encoder_root) for name in encoders}
    for encoder in encoders:
        extractor = extractors[encoder]
        matrices[encoder] = features(payloads, extractor)
        # Each augmented view belongs to a train subject, never validation/test.
        views[encoder] = np.stack(
            [
                features((perturb(payloads[i], kind) for i in train), extractor)
                for kind in ("lighting", "crop")
            ]
        )
    encoder, head, report = select_model(matrices, y, subjects, seed=seed, train_views=views)
    report["cohorts"] = {}
    for cohort in sorted({cohorts[i] for i in test}):
        indices = np.asarray([i for i in test if cohorts[i] == cohort], dtype=int)
        report["cohorts"][cohort] = {
            **metrics(head.predict(matrices[encoder][indices]), y[indices]),
            "subjects": len({subjects[i] for i in indices}),
        }
    clean = head.predict(matrices[encoder][test])
    report["perturbations"] = {}
    for kind in ("lighting", "crop", "rotation"):
        changed = features((perturb(payloads[i], kind) for i in test), extractors[encoder])
        prediction = head.predict(changed)
        report["perturbations"][kind] = {
            **metrics(prediction, y[test]),
            "mean_absolute_drift": float(np.abs(prediction - clean).mean()),
        }
    report["pose_review_reference"] = pose_review
    sources = [
        Path(__file__).with_name(name)
        for name in ("native.py", "native_data.py", "native_train.py", "native_checkpoint.py")
    ]
    report["implementation_sha256"] = hashlib.sha256(
        b"".join(p.read_bytes() for p in sources)
    ).hexdigest()
    report["labels_sha256"] = hashlib.sha256(labels.read_bytes()).hexdigest()
    report["objective"] = "sum squared errors + alpha * squared weight norm; bounded output 1–5"
    report["augmentation"] = "train only: clean + brightness 0.85 + central 90% crop"
    report["test_policy"] = "winner fixed by validation MAE; no test-based selection"
    return head, new_manifest(encoder, plan, digest, head, report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("labels", "images", "plan", "encoder-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--pose-review", default="")
    args = parser.parse_args()
    try:
        plan = Collection.model_validate_json(args.plan.read_bytes())
        head, item = run(
            args.labels,
            args.images,
            plan,
            args.encoder_root,
            seed=args.seed,
            pose_review=args.pose_review,
        )
        pin = write(args.output, head, item)
        print(
            json.dumps(
                {
                    "manifest_sha256": pin,
                    "release_failures": release_failures(item),
                    "report": item.report,
                },
                allow_nan=False,
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        # Never print private filenames/identities or rejected input.
        print(f"Native training refused: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
