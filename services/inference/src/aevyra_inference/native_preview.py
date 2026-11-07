"""Explicit laboratory capability, separate from the release-gated ModelProvider.

Only a pinned, human-trained 1–7 checkpoint with recorded research rights is eligible.
This is NOT a release review, calibration, or authorization for consumer scoring.
"""

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

from aevyra_inference.extractors import create_extractor
from aevyra_inference.native import NativeHead
from aevyra_inference.native_checkpoint import Manifest, load, release_failures


def reviewed_checkpoint(root: Path, pin: str) -> tuple[NativeHead, Manifest]:
    """Load and hash-verify the pinned checkpoint once, then apply the preview review."""
    head, item = load(root, pin, require_release=False)
    if item.collection.synthetic or item.native_scale != (1, 7):
        raise ValueError("Preview requires a human-trained native 1–7 checkpoint")
    # Rights are independently pinned as part of the manifest, never inferred from a URL.
    if not all(r.research_allowed and r.adult_confirmed for r in item.collection.rights.values()):
        raise ValueError("Research rights review missing")
    return head, item


def reviewed(root: Path, pin: str) -> Manifest:
    return reviewed_checkpoint(root, pin)[1]


def predict(root: Path, pin: str, encoder_root: Path, image: bytes) -> dict[str, object]:
    started = time.perf_counter()
    head, item = reviewed_checkpoint(root, pin)
    extractor = create_extractor(item.encoder, encoder_root)
    value = float(head.predict(np.asarray(extractor.extract_batch([image])))[0])
    if not np.isfinite(value) or not 1 <= value <= 7:
        raise ValueError("Invalid native prediction")
    return {
        "predicted_rating": value,
        "native_scale": [1, 7],
        "manifest_sha256": pin,
        "encoder": item.encoder,
        "collection": item.collection.name,
        "research_only": True,
        "synthetic": False,
        "consumer_enabled": False,
        "release_failures": release_failures(item),
        "duration_ms": (time.perf_counter() - started) * 1000,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def main() -> None:
    # Dedicated killable, one-thread subprocess. No weights downloaded or substituted.
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    args = json.loads(sys.stdin.read(4096))
    image = Path(args["image"])
    if image.is_symlink() or image.stat().st_size > 50 * 1024**2:
        raise ValueError("Invalid private image")
    result = predict(
        Path(args["checkpoint"]), args["pin"], Path(args["encoder_root"]), image.read_bytes()
    )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
