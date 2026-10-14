"""Synthetic resource benchmark. Never downloads or reads personal photographs.

Example: OPENBLAS_NUM_THREADS=1 uv run python scripts/benchmark-preference-extractors.py
--extractor mobilenetv3-small-imagenet-onnx-v1 --root private-data/pretrained --count 500
"""

import argparse
import importlib.metadata
import json
import platform
import resource
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from aevyra_inference.extractors import BASELINE, MOBILENET, create_extractor, manifest
from aevyra_inference.preference import predictions, train
from PIL import Image


def synthetic(index: int) -> bytes:
    rng = np.random.default_rng(index)
    small = rng.integers(0, 256, (16, 16, 3), dtype=np.uint8)
    output = BytesIO()
    Image.fromarray(small).resize((256, 256), Image.Resampling.BILINEAR).save(output, "JPEG")
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extractor", choices=[BASELINE, MOBILENET], required=True)
    parser.add_argument("--root", type=Path, default=Path("private-data/pretrained"))
    parser.add_argument("--count", type=int, choices=[50, 500, 1000], default=500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    extractor = create_extractor(args.extractor, args.root)
    initialization = time.perf_counter() - started
    # Only compressed synthetic fixtures are retained in memory, not full-size RGB arrays.
    payloads = [synthetic(i) for i in range(args.count)]
    started, cpu_started = time.perf_counter(), time.process_time()
    features = []
    for index in range(0, args.count, 8):
        features.extend(extractor.extract_batch(payloads[index : index + 8]))
    extraction, extraction_cpu = time.perf_counter() - started, time.process_time() - cpu_started
    latencies = []
    for payload in payloads[:30]:
        before = time.perf_counter()
        extractor.extract_batch([payload])
        latencies.append((time.perf_counter() - before) * 1000)
    report = {
        "dataset": "generated synthetic texture images; arbitrary simulated ratings; NOT faces",
        "measured_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "cpu_quota": Path("/sys/fs/cgroup/cpu.max").read_text().strip(),
        "memory_limit_bytes": int(Path("/sys/fs/cgroup/memory.max").read_text()),
        "facial_accuracy_evidence": False,
        "count": args.count,
        "extractor": args.extractor,
        "manifest": manifest(args.extractor),
        "initialization_seconds": initialization,
        "batch_size": 8,
        "extraction_wall_seconds": extraction,
        "extraction_cpu_seconds": extraction_cpu,
        "extraction_images_per_second": args.count / extraction,
        "single_extraction_p50_ms": float(np.median(latencies)),
        "single_extraction_p95_ms": float(np.percentile(latencies, 95)),
        "compressed_synthetic_input_bytes": sum(map(len, payloads)),
        "embedding_float32_bytes": args.count * len(features[0]) * 4,
        "embedding_json_bytes": len(json.dumps(features).encode()),
        "application_quota": 500,
    }
    if args.count <= 500:
        ratings = [1 + (i % 10) for i in range(args.count)]
        groups = [f"synthetic-person-{i // 2}" for i in range(args.count)]
        before = time.perf_counter()
        checkpoint, measured, training, heldout = train(
            features,
            ratings,
            groups,
            alpha=10,
            seed=42,
            validation_fraction=0.2,
            rating_min=1,
            rating_max=10,
            snapshot_sha256="a" * 64,
            check=lambda: None,
            extractor=args.extractor,
        )
        fit_seconds = time.perf_counter() - before
        raw_latency = []
        for _ in range(30):
            before = time.perf_counter()
            predictions(checkpoint, np.asarray([features[0]], dtype=np.float64))
            raw_latency.append((time.perf_counter() - before) * 1000)
        report.update(
            {
                "fit_validation_seconds": fit_seconds,
                "synthetic_validation": measured,
                "training_images": len(training),
                "heldout_images": len(heldout),
                "checkpoint_bytes": len(checkpoint.model_dump_json().encode()),
                "cached_regression_p50_ms": float(np.median(raw_latency)),
            }
        )
    else:
        report["training"] = (
            "Not attempted: existing application quota remains 500. Extraction scaling only."
        )
    report["peak_process_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    report["runtime_distribution_bytes"] = {
        package: sum(
            file.locate().stat().st_size
            for file in importlib.metadata.distribution(package).files or []
            if file.locate().is_file()
        )
        for package in ("onnxruntime", "numpy", "pillow")
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered)


if __name__ == "__main__":
    main()
