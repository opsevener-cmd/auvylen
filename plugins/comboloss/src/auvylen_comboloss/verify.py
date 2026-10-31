"""Offline reference/CPU check after rights review; never creates or changes a manifest.

Usage: python -m auvylen_comboloss.verify ROOT REFERENCES.json
References: [{"image": "/private/authorized.png", "expected": <official regression>}]
Expected values must come from the pinned upstream code and the same canonical RGB PNGs.
"""

import hashlib
import json
import resource
import statistics
import sys
import time
from pathlib import Path

from auvylen_comboloss import Provider


def main():
    references = json.loads(Path(sys.argv[2]).read_text())
    if not isinstance(references, list) or len(references) < 3:
        raise ValueError("At least three independent official reference predictions required")
    started = time.perf_counter()
    engine = Provider().load(Path(sys.argv[1]))
    cold_ms = (time.perf_counter() - started) * 1000
    rows = []
    for reference in references:
        image = Path(reference["image"]).read_bytes()
        prepared = engine.preprocess(image)
        timings = []
        for _ in range(10):
            before = time.perf_counter()
            value = engine.predict(prepared)
            timings.append((time.perf_counter() - before) * 1000)
            if abs(value - reference["expected"]) > 1e-5:
                raise ValueError("Official reference prediction mismatch")
        rows.append(
            {
                "image_sha256": hashlib.sha256(image).hexdigest(),
                "absolute_error": abs(value - reference["expected"]),
                "median_decode_preprocess_forward_ms": statistics.median(timings),
            }
        )
    print(
        json.dumps(
            {
                "cold_load_ms": cold_ms,
                "peak_process_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "references": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
