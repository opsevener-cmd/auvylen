"""Explicit offline research inference on an unreleased HUMAN-trained checkpoint.

Not a ModelProvider, not registered in the API, never overrides product release gates.
Individual predictions go only to a new private output file; stdout is timing evidence.
"""

import argparse
import hashlib
import json
import os
import resource
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from aevyra_inference.extractors import create_extractor
from aevyra_inference.native_checkpoint import load, release_failures


def inspect(
    root: Path, pin: str, encoder_root: Path, image: Path, output: Path, *, repeats: int = 30
) -> dict[str, object]:
    if not 3 <= repeats <= 100:
        raise ValueError("Research timing needs 3–100 repetitions")
    if image.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Image byte limit")
    started = time.perf_counter()
    head, item = load(root, pin, require_release=False)
    if item.collection.synthetic:
        raise ValueError("Offline portrait inspection requires human training data")
    extractor = create_extractor(item.encoder, encoder_root)
    model_load_ms = (time.perf_counter() - started) * 1000
    payload = image.read_bytes()
    started = time.perf_counter()
    initial_features = np.asarray(extractor.extract_batch([payload]))
    initial = float(head.predict(initial_features)[0])
    first_prediction_ms = (time.perf_counter() - started) * 1000
    timings, maximum = [], 0.0
    for _ in range(repeats):
        started = time.perf_counter()
        prediction = float(head.predict(np.asarray(extractor.extract_batch([payload])))[0])
        timings.append((time.perf_counter() - started) * 1000)
        maximum = max(maximum, abs(initial - prediction))
    reloaded, _ = load(root, pin, require_release=False)
    parity = abs(initial - float(reloaded.predict(initial_features)[0]))
    if maximum > 1e-8 or parity > 1e-8:
        raise ValueError("Saved model inference parity failed")
    record = {
        "predicted_rating": initial,
        "native_scale": list(item.native_scale),
        "manifest_sha256": pin,
        "head_sha256": item.weights_sha256,
        "image_sha256": hashlib.sha256(payload).hexdigest(),
        "timestamp": datetime.now(UTC).isoformat(),
        "research_only": True,
        "release_failures": release_failures(item),
    }
    with output.open("x") as f:
        os.chmod(output, 0o600)
        json.dump(record, f, allow_nan=False, indent=2)
    return {
        "scope": (
            "real human-trained checkpoint and authorized held-out portrait; offline research only"
        ),
        "encoder": item.encoder,
        "native_scale": list(item.native_scale),
        "cold_model_load_ms": model_load_ms,
        "first_portrait_decode_encoder_head_ms": first_prediction_ms,
        "warm_portrait_decode_encoder_head_median_ms": statistics.median(timings),
        "warm_p95_ms": float(np.quantile(timings, 0.95)),
        "repetitions": repeats,
        "peak_process_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "head_bytes": (root / "head.f64").stat().st_size,
        "max_prediction_drift": maximum,
        "saved_head_reload_difference": parity,
        "manifest_sha256": pin,
        "release_failures": release_failures(item),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("checkpoint", "encoder-root", "image", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    args = p.parse_args()
    print(
        json.dumps(
            inspect(
                args.checkpoint, args.manifest_sha256, args.encoder_root, args.image, args.output
            ),
            indent=2,
        )
    )
