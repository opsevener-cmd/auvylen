"""Pinned, licence-reviewed frozen encoders and resumable embedding.

Only revisions listed here are loaded; nothing floats to "main". ``deployable`` marks
encoders whose licence and model card permit a later service-use review. OpenAI CLIP's
model card places *any* deployed use out of scope, so it is a research comparison only.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from auvylen7b.data import Dataset
from auvylen7b.store import Store, key


@dataclass(frozen=True)
class Encoder:
    name: str
    repo: str
    revision: str
    licence: str
    deployable: bool
    kind: str  # "dinov2" | "siglip" | "clip" | "timm"


ENCODERS = {
    e.name: e
    for e in (
        Encoder(
            "dinov2-small",
            "facebook/dinov2-small",
            "ed25f3a31f01632728cabb09d1542f84ab7b0056",
            "Apache-2.0",
            True,
            "dinov2",
        ),
        Encoder(
            "dinov2-base",
            "facebook/dinov2-base",
            "f9e44c814b77203eaa57a6bdbbd535f21ede1415",
            "Apache-2.0",
            True,
            "dinov2",
        ),
        Encoder(
            "siglip-base",
            "google/siglip-base-patch16-224",
            "7fd15f0689c79d79e38b1c2e2e2370a7bf2761ed",
            "Apache-2.0",
            True,
            "siglip",
        ),
        Encoder(
            "clip-b16",
            "openai/clip-vit-base-patch16",
            "57c216476eefef5ab752ec549e440a49ae4ae5f3",
            "MIT code; model card: deployed use out of scope",
            False,
            "clip",
        ),
        # Reference: the current pilot encoder's source checkpoint (aggregate ONNX parity verified).
        Encoder(
            "mobilenetv3-small",
            "timm/mobilenetv3_small_100.lamb_in1k",
            "76b303ec28c466e9df37f4745dfb7aef20ab87ae",
            "Apache-2.0",
            True,
            "timm",
        ),
    )
}
VIEWS = ("clean", "mirror", "lighting", "crop")


def view(payload: bytes, kind: str) -> Image.Image:
    with Image.open(io.BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    if kind == "mirror":
        return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    if kind == "lighting":  # Same perturbations as aevyra_inference.native_data.perturb.
        return ImageEnhance.Brightness(image).enhance(0.85)
    if kind == "crop":
        w, h = image.size
        return image.crop((round(w * 0.05), round(h * 0.05), round(w * 0.95), round(h * 0.95)))
    if kind != "clean":
        raise ValueError("Unknown view")
    return image


def load(encoder: Encoder, device: str):  # pragma: no cover - needs torch and network
    import torch

    if encoder.kind == "timm":
        import timm
        from huggingface_hub import hf_hub_download

        weights = hf_hub_download(encoder.repo, "model.safetensors", revision=encoder.revision)
        model = timm.create_model(
            "mobilenetv3_small_100.lamb_in1k",
            pretrained=True,
            num_classes=0,
            pretrained_cfg_overlay={"file": weights},
        )
        config = timm.data.resolve_data_config({}, model=model)
        transform = timm.data.create_transform(**config)
        prepare = lambda images: torch.stack([transform(i) for i in images])  # noqa: E731
        forward = lambda x: model(x)  # noqa: E731
    else:
        from transformers import (
            AutoImageProcessor,
            AutoModel,
            CLIPVisionModelWithProjection,
            SiglipVisionModel,
        )

        cls = {
            "dinov2": AutoModel,
            "siglip": SiglipVisionModel,
            "clip": CLIPVisionModelWithProjection,
        }[encoder.kind]
        model = cls.from_pretrained(encoder.repo, revision=encoder.revision)
        processor = AutoImageProcessor.from_pretrained(encoder.repo, revision=encoder.revision)
        prepare = lambda images: processor(images=images, return_tensors="pt")["pixel_values"]  # noqa: E731
        if encoder.kind == "clip":
            forward = lambda x: model(pixel_values=x).image_embeds  # noqa: E731
        else:
            forward = lambda x: model(pixel_values=x).pooler_output  # noqa: E731
    model = model.eval().to(device)
    return prepare, forward


def embed(
    store: Store,
    dataset: Dataset,
    encoders: Iterable[str],
    *,
    device: str,
    batch: int = 32,
    loader=None,
) -> dict[str, str]:
    """Embed every (encoder, view) pair; returns the shard key per pair. Resumes per shard."""
    import contextlib

    try:
        import torch

        no_grad = torch.inference_mode
    except ImportError:  # Generated-feature tests only.
        no_grad = contextlib.nullcontext
    loader = loader or load
    done: dict[str, str] = {}
    shas = [item.sha256 for item in dataset.items]
    for name in encoders:
        encoder = ENCODERS[name]
        loaded = None
        for kind in VIEWS:
            unit = key(
                "embed", {"encoder": encoder.revision, "name": name, "view": kind, "images": shas}
            )
            relative = f"embeddings/{name}/{unit}.npz"
            done[f"{name}/{kind}"] = relative
            if store.exists(relative):
                continue
            if loaded is None:
                loaded = loader(encoder, device)
            prepare, forward = loaded
            chunks = []
            with no_grad():
                for start in range(0, len(dataset.items), batch):
                    images = [view(i.payload(), kind) for i in dataset.items[start : start + batch]]
                    output = (
                        forward(prepare(images).to(device))
                        if device != "numpy"
                        else forward(prepare(images))
                    )
                    chunks.append(
                        np.asarray(
                            output.float().cpu().numpy() if hasattr(output, "cpu") else output,
                            dtype=np.float32,
                        )
                    )
            features = np.concatenate(chunks)
            if not np.isfinite(features).all():
                raise ValueError("Non-finite embedding")
            store.write_arrays(relative, features=features, sha256=np.asarray(shas))
            store.record(
                unit,
                stage="embed",
                encoder=name,
                revision=encoder.revision,
                view=kind,
                images=len(shas),
                dim=int(features.shape[1]),
                synthetic=dataset.synthetic,
            )
    return done
