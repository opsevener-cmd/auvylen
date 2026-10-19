"""Compare legacy JSON/base64 and binary ingestion using generated noise, never private data.

Run: uv run python scripts/benchmark-upload-transport.py
Times include request parsing and image sanitization, excluding network/database storage.
tracemalloc measures Python allocations only, not Pillow/native memory or total RSS.
"""

import base64
import gc
import json
import random
import statistics
import time
import tracemalloc
from io import BytesIO

from aevyra_api.preferences.images import decode_image, decode_image_bytes
from aevyra_contracts.preferences import ImageUpload, ImageUploadMetadata
from PIL import Image


def main() -> None:
    stream = BytesIO()
    Image.frombytes("RGB", (1024, 1024), random.Random(42).randbytes(1024 * 1024 * 3)).save(
        stream, format="PNG"
    )
    binary = stream.getvalue()
    metadata = {"adult_authorized_consent": True, "subject_group": "generated-fixture"}
    legacy = json.dumps(
        {**metadata, "content_base64": base64.b64encode(binary).decode()}, separators=(",", ":")
    ).encode()
    header = json.dumps(metadata).encode()
    output: dict[str, object] = {
        "fixture": "Deterministic 1024x1024 RGB noise PNG; no faces or personal data",
        "repetitions": 5,
        "binary_body_bytes": len(binary),
        "legacy_body_bytes": len(legacy),
        "body_reduction_percent": round(100 * (1 - len(binary) / len(legacy)), 2),
        "scope": "parse+sanitize; excludes network/database and native/Pillow allocations",
    }
    hashes: set[str] = set()
    for name in ("legacy", "binary"):
        elapsed, cpu, peaks = [], [], []
        for _ in range(5):
            gc.collect()
            tracemalloc.start()
            started, cpu_started = time.perf_counter(), time.process_time()
            if name == "legacy":
                body = ImageUpload.model_validate_json(legacy)
                result = decode_image(body.content_base64)
            else:
                ImageUploadMetadata.model_validate_json(header)
                result = decode_image_bytes(binary)
            elapsed.append((time.perf_counter() - started) * 1000)
            cpu.append((time.process_time() - cpu_started) * 1000)
            peaks.append(tracemalloc.get_traced_memory()[1])
            tracemalloc.stop()
            hashes.add(result.content_hash)
        output[name] = {
            "median_ms": round(statistics.median(elapsed), 2),
            "median_cpu_ms": round(statistics.median(cpu), 2),
            "median_peak_python_bytes": int(statistics.median(peaks)),
        }
    assert len(hashes) == 1, "Transport must preserve normalized pixels"
    output["identical_normalized_pixels"] = True
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
