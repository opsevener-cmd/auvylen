"""Versioned, first-party feature extraction, independent of scoring plugins.

No runtime downloads. Only the pinned, reviewed ONNX checkpoint is accepted.
"""

import hashlib
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageOps
from PIL import __version__ as pillow_version
from pydantic import JsonValue

BASELINE = "rgb-grid-texture-v1"
MOBILENET = "mobilenetv3-small-imagenet-onnx-v1"
WEIGHT_FILE = "mobilenetv3-small-100-lamb-embedding-v1.onnx"
WEIGHT_SHA256 = "164c481657afe9d36e08ff58693df24e511b5bf1a07de9b9389dfc468eedd2a6"
WEIGHT_BYTES = 6_078_515
SOURCE_REVISION = "0df212b369a5385b16dfe513d5143a7311ea1ddc"
SOURCE_SHA256 = "266a294cbf3d119000a760bf5664a4d80a9674d0616b5cc0836b093d20c38249"
SOURCE = (
    "https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/"
    "mobilenetv3_small_100_lamb-266a294c.pth"
)
BATCH_SIZE = 8


def dimension(identifier: str) -> int:
    if identifier == BASELINE:
        return 230
    if identifier == MOBILENET:
        return 1024
    raise ValueError("Unknown feature extractor")


def manifest(identifier: str) -> dict[str, JsonValue]:
    dimension(identifier)
    if identifier == BASELINE:
        return {"id": BASELINE, "dimension": 230, "preprocessing": "rgb-grid-texture-v1"}
    return {
        "id": MOBILENET,
        "dimension": 1024,
        "architecture": "MobileNetV3-Small width 1.0, frozen ImageNet ILSVRC2012",
        "model_version": "timm mobilenetv3_small_100.lamb_in1k; timm 1.0.30; ONNX opset 17",
        "source": SOURCE,
        "source_revision": SOURCE_REVISION,
        "source_weight_sha256": SOURCE_SHA256,
        "source_weight_bytes": 10_256_237,
        "weight_sha256": WEIGHT_SHA256,
        "weight_bytes": WEIGHT_BYTES,
        "weight_license": "Apache-2.0",
        "code_licenses": (
            "timm/ONNX Apache-2.0; PyTorch/TorchVision BSD-3-Clause; "
            "ONNX Runtime MIT; NumPy BSD-3-Clause; Pillow MIT-CMU"
        ),
        "preprocessing": (
            "exif-transpose RGB; shorter edge 256 bicubic; center crop 224; float32 /255; NCHW"
        ),
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "output": (
            "1024 penultimate features; global average pooling, conv_head, "
            "hardswish; classifier removed"
        ),
        "graph_transform": (
            "timm reset_classifier(0); torch 2.10.0+cpu legacy export; dynamic batch; opset 17"
        ),
        "export_toolchain": (
            "timm==1.0.30; torch==2.10.0+cpu; torchvision==0.25.0+cpu; onnx==1.22.0"
        ),
        "runtime": "onnxruntime==1.31.0; CPUExecutionProvider; sequential; 1 thread",
        "pillow": "12.3.0",
        "numpy": "2.5.4",
        "batch_size": BATCH_SIZE,
        "telemetry": "disabled",
    }


def verified_weights(root: Path) -> bytes:
    path = root / WEIGHT_FILE
    if not path.is_file() or path.stat().st_size != WEIGHT_BYTES:
        raise ValueError("Reviewed MobileNet weights unavailable; ask the operator to install them")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != WEIGHT_SHA256:
        raise ValueError("MobileNet weight checksum mismatch")
    return data


def availability(identifier: str, root: Path) -> tuple[bool, str]:
    dimension(identifier)
    if identifier == BASELINE:
        return True, "Built-in handcrafted features"
    try:
        verified_weights(root)
    except (OSError, ValueError):
        return False, "Reviewed MobileNet checkpoint missing or checksum invalid"
    return True, "Verified pretrained checkpoint installed"


class FeatureExtractor(Protocol):
    identifier: str

    def extract_batch(self, payloads: Sequence[bytes]) -> list[list[float]]: ...


class HandcraftedExtractor:
    identifier = BASELINE

    def extract_batch(self, payloads: Sequence[bytes]) -> list[list[float]]:
        from aevyra_inference.preference import extract

        if not 1 <= len(payloads) <= BATCH_SIZE:
            raise ValueError("Feature batch limit")
        return [extract(payload) for payload in payloads]


class MobileNetExtractor:
    identifier = MOBILENET

    def __init__(self, root: Path):
        # Imports are worker-only: API availability checks never initialize an ML runtime.
        import onnxruntime as ort  # type: ignore[import-untyped]  # Upstream has no typing marker.

        if ort.__version__ != "1.31.0" or pillow_version != "12.3.0" or np.__version__ != "2.5.4":
            raise ValueError("Extractor runtime version mismatch")
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            verified_weights(root), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_name = "images"

    def extract_batch(self, payloads: Sequence[bytes]) -> list[list[float]]:
        if not 1 <= len(payloads) <= BATCH_SIZE:
            raise ValueError("Feature batch limit")
        prepared = []
        for payload in payloads:
            if len(payload) > 10 * 1024 * 1024:
                raise ValueError("Image size limit")
            with Image.open(BytesIO(payload), formats=["JPEG", "PNG"]) as image:
                if (
                    image.width > 4096
                    or image.height > 4096
                    or image.width * image.height > 16_000_000
                    or getattr(image, "n_frames", 1) != 1
                ):
                    raise ValueError("Image dimensions/frame limit")
                rgb = ImageOps.exif_transpose(image).convert("RGB")
                w, h = rgb.size
                # Bound resized memory even for hostile extremely narrow images.
                if max(w, h) / min(w, h) > 8:
                    raise ValueError("Image aspect ratio exceeds pretrained extractor limit (8:1)")
                size = (int(w * 256 / min(w, h)), int(h * 256 / min(w, h)))
                rgb = rgb.resize(size, Image.Resampling.BICUBIC)
                left, top = round((size[0] - 224) / 2), round((size[1] - 224) / 2)
                pixels = (
                    np.asarray(rgb.crop((left, top, left + 224, top + 224)), dtype=np.float32) / 255
                )
            pixels = (pixels - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
                [0.229, 0.224, 0.225], dtype=np.float32
            )
            prepared.append(pixels.transpose(2, 0, 1))
        values = np.asarray(self.session.run(None, {self.input_name: np.stack(prepared)})[0])
        values = values.reshape(len(payloads), -1)
        if values.shape != (len(payloads), 1024) or not np.isfinite(values).all():
            raise ValueError("Invalid pretrained features")
        return [[float(value) for value in row] for row in values]


def create_extractor(identifier: str, root: Path) -> FeatureExtractor:
    dimension(identifier)
    return HandcraftedExtractor() if identifier == BASELINE else MobileNetExtractor(root)
