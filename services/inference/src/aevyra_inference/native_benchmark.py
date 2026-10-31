"""Isolated CPU encoder benchmark on generated pixels, NOT aesthetic validation."""

import argparse
import hashlib
import json
import resource
import statistics
import time
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from aevyra_inference.extractors import BASELINE, MOBILENET, create_extractor, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder", choices=[BASELINE, MOBILENET], required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    pixels = np.random.default_rng(42).integers(0, 256, (320, 256, 3), dtype=np.uint8)
    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, "JPEG", quality=90)
    payload = buffer.getvalue()
    start = time.perf_counter()
    extractor = create_extractor(args.encoder, args.root)
    cold_ms = (time.perf_counter() - start) * 1000
    reference = np.asarray(extractor.extract_batch([payload]))
    times = []
    max_difference = 0.0
    for _ in range(30):
        start = time.perf_counter()
        actual = np.asarray(extractor.extract_batch([payload]))
        times.append((time.perf_counter() - start) * 1000)
        max_difference = max(max_difference, float(np.abs(reference - actual).max()))
        if not np.allclose(reference, actual, rtol=0, atol=1e-8):
            raise ValueError("Encoder repeated-inference mismatch")
    print(
        json.dumps(
            {
                "purpose": "generated-pixel encoder timing only; no aesthetic head or score",
                "encoder": args.encoder,
                "manifest": manifest(args.encoder),
                "input_sha256": hashlib.sha256(payload).hexdigest(),
                "cold_load_ms": cold_ms,
                "warm_decode_preprocess_encoder_median_ms": statistics.median(times),
                "warm_p95_ms": float(np.quantile(times, 0.95)),
                "repetitions": len(times),
                "peak_process_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "feature_dimension": int(reference.shape[1]),
                "max_repeated_difference": max_difference,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
