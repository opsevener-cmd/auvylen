"""CPU cost of the Phase 6 aesthetic head on generated data (no photographs, no quality claim).

Usage: uv run python scripts/benchmark-aesthetic.py [--output docs/phase6/cpu-benchmark.json]
MobileNet extraction cost is measured by scripts/benchmark-preference-extractors.py with
reviewed weights installed; this script covers the head and the built-in handcrafted extractor.
"""

import argparse
import json
import os
import platform
import statistics
import time
import tracemalloc
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

import numpy as np
from aevyra_inference.aesthetic import analyze, fit_scoring_head
from aevyra_inference.extractors import HandcraftedExtractor
from PIL import Image


def generated(images: int, d: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray, list[str]]:
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, (images, d))
    quality = x @ rng.normal(0, 1, d) / np.sqrt(d)
    votes = []
    for q in quality:
        p = np.exp(-((np.arange(5) - 2 - q) ** 2))
        votes.append(rng.multinomial(20, p / p.sum()))
    return x, np.asarray(votes, dtype=float), [f"s{i // 3}" for i in range(images)]


def median_ms(action: Callable[[], object], repeats: int) -> float:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report: dict[str, object] = {
        "scope": "Generated vectors and a generated 320x400 PNG; CPU timing only, not accuracy.",
        "python": platform.python_version(),
        "numpy": np.__version__,
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS", "default"),
    }
    training = []
    for images, d in ((600, 230), (600, 1024), (5000, 1024)):
        x, votes, ids = generated(images, d)
        tracemalloc.start()
        started = time.perf_counter()
        _, metrics = fit_scoring_head(x, votes, ids)
        seconds = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        training.append(
            {
                "images": images,
                "dimension": d,
                "epochs_run": metrics["epochs_run"],
                "seconds": round(seconds, 3),
                "peak_traced_mib": round(peak / 2**20, 1),
            }
        )
    report["training"] = training
    x, votes, ids = generated(600, 1024)
    head, _ = fit_scoring_head(x, votes, ids, epochs=5)
    report["head_inference_ms_per_image_1024"] = round(
        median_ms(lambda: analyze(head, x[0]), 200), 4
    )
    pixels = np.linspace(0, 255, 320 * 400 * 3).reshape(400, 320, 3).astype("uint8")
    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, "PNG")
    payload = buffer.getvalue()
    extractor = HandcraftedExtractor()
    report["handcrafted_extraction_ms_per_image"] = round(
        median_ms(lambda: extractor.extract_batch([payload]), 30), 2
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")


if __name__ == "__main__":
    main()
