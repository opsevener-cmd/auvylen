"""Real reviewed MobileNet + aesthetic training/checkpoint/inference on generated pixels.

Engineering/performance verification only. Simulated votes are NOT human labels and this
checkpoint is never enabled in the application. Private model artifacts stay in a temp dir.
"""

import argparse
import json
import statistics
import tempfile
import time
from io import BytesIO
from pathlib import Path

import numpy as np
from aevyra_inference.aesthetic import analyze, fit_scoring_head
from aevyra_inference.aesthetic_checkpoint import DatasetEvidence, load_checkpoint, write_checkpoint
from aevyra_inference.extractors import MOBILENET, WEIGHT_SHA256, create_extractor
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretrained-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rng = np.random.default_rng(6)
    payloads = []
    for _ in range(96):
        pixels = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
        stream = BytesIO()
        Image.fromarray(pixels).save(stream, "PNG")
        payloads.append(stream.getvalue())
    extractor = create_extractor(MOBILENET, args.pretrained_root)
    started = time.perf_counter()
    rows = []
    for start in range(0, len(payloads), 8):
        rows.extend(extractor.extract_batch(payloads[start : start + 8]))
    extraction_seconds = time.perf_counter() - started
    features = np.asarray(rows)
    # Generated categorical counts exercise training; no aesthetic validity is claimed.
    votes = rng.multinomial(25, [0.1, 0.2, 0.4, 0.2, 0.1], size=len(rows))
    head, metrics = fit_scoring_head(features, votes, [f"generated-{i // 3}" for i in range(96)])
    evidence = DatasetEvidence(
        name="Generated noise verification",
        license="Generated test-only",
        terms_url="https://example.invalid/test",
        authorization_reference="TEST-ONLY",
        reviewer="automated verification",
        annotator_population="simulated counts",
        adult_subjects_confirmed=True,
        synthetic=True,
        rating_scale="five ordered categories, 1 (lowest) to 5 (highest)",
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        _, sha = write_checkpoint(
            root,
            head,
            model_version="synthetic-mobilenet-check",
            extractor=MOBILENET,
            dataset=evidence,
            training={"purpose": "engineering verification"},
            metrics=metrics,
        )
        loaded = load_checkpoint(root, "synthetic-mobilenet-check", sha)
        np.testing.assert_array_equal(head.weights, loaded.head.weights)

        def inference(cold: bool) -> dict:
            model = load_checkpoint(root, "synthetic-mobilenet-check", sha) if cold else loaded
            visual = create_extractor(MOBILENET, args.pretrained_root) if cold else extractor
            return analyze(model.head, visual.extract_batch([payloads[0]])[0])

        samples = {}
        for mode in ("warm", "cold"):
            elapsed = []
            for _ in range(20):
                started = time.perf_counter()
                result = inference(mode == "cold")
                elapsed.append(1000 * (time.perf_counter() - started))
                assert 1 <= result["score_10"] <= 10
                assert abs(sum(result["rating_distribution"]) - 1) < 1e-10
            samples[mode] = {
                "median_ms": statistics.median(elapsed),
                "p95_ms": float(np.percentile(elapsed, 95)),
            }
    report = {
        "scope": (
            "Generated PNG -> real MobileNet CPU -> aesthetic head; cold includes pinned "
            "checkpoint verification and ONNX session creation; excludes HTTP/queue/database "
            "latency. Not human aesthetic validation."
        ),
        "reviewed_weight_sha256": WEIGHT_SHA256,
        "images": len(rows),
        "feature_shape": list(features.shape),
        "batch_extraction_seconds": extraction_seconds,
        "timings": samples,
        "checkpoint_round_trip": True,
        "synthetic": True,
        "application_scoring_enabled": False,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
