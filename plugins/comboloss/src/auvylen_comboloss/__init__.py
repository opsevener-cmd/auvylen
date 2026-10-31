"""Optional ComboLoss adapter. No downloads, face detection, calibration or retraining."""

import hashlib
import importlib.util
import json
import math
import os
from io import BytesIO
from pathlib import Path

from aevyra_contracts import EngineMetadata
from aevyra_inference.engine import ScoringEngine
from aevyra_inference.providers import ProviderStatus

SOURCE = "2543efff58b287cb7b0ca4f7665d36855e8c62d9"
MAX_CHECKPOINT = 160 * 1024 * 1024


def verified(root: Path) -> dict:
    manifest = root / "manifest.json"
    if manifest.is_symlink() or manifest.stat().st_size > 16384:
        raise ValueError("Invalid manifest")
    raw = manifest.read_bytes()
    pin = os.environ.get("COMBOLOSS_MANIFEST_SHA256", "")
    if len(pin) != 64 or hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError("Manifest integrity failure")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid manifest shape")
    if data.get("source_commit") != SOURCE or data.get("native_scale") != [1, 5]:
        raise ValueError("Unsupported model version")
    rights = data.get("rights", {})
    if not isinstance(rights, dict):
        raise PermissionError("Unreviewed license")
    if not all(
        isinstance(rights.get(k), str) and rights[k].strip()
        for k in ("reviewer", "code_license", "weights_permission", "dataset_permission")
    ):
        raise PermissionError("Unreviewed license")
    if rights.get("research_service_allowed") is not True:
        raise PermissionError("Research service not authorized")
    if data.get("reference_verified") is not True:
        raise ValueError("Reference inference has not been verified")
    checkpoint = root / "checkpoint.pth"
    if checkpoint.is_symlink() or not 0 < checkpoint.stat().st_size <= MAX_CHECKPOINT:
        raise ValueError("Invalid checkpoint")
    with checkpoint.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != data.get("checkpoint_sha256"):
        raise ValueError("Checkpoint integrity failure")
    return data


class Provider:
    def availability(self, model_root: Path) -> ProviderStatus:
        try:
            verified(model_root)
            if any(
                importlib.util.find_spec(name) is None
                for name in ("torch", "torchvision", "pytorchcv")
            ):
                return ProviderStatus("comboloss", "ComboLoss", False, "missing_dependencies")
        except FileNotFoundError:
            return ProviderStatus("comboloss", "ComboLoss", False, "missing_weights")
        except PermissionError:
            return ProviderStatus("comboloss", "ComboLoss", False, "unreviewed_license")
        except (ValueError, KeyError, TypeError, OSError):
            return ProviderStatus(
                "comboloss", "ComboLoss", False, "dependency_or_configuration_error"
            )
        return ProviderStatus("comboloss", "ComboLoss", True, "ready")

    def load(self, model_root: Path) -> ScoringEngine:
        return ComboLoss(model_root)


class ComboLoss(ScoringEngine):
    def __init__(self, root: Path):
        self.manifest = verified(root)
        import torch
        from pytorchcv.model_provider import get_model
        from torch import nn
        from torchvision import transforms

        torch.set_num_threads(1)

        # Same architecture/state-dict names as official models/nets.py; no ImageNet download.
        class ComboNet(nn.Module):
            def __init__(self):
                super().__init__()
                backbone = get_model("seresnext50_32x4d", pretrained=False)
                self.backbone = backbone.features
                self.regression_branch = nn.Linear(backbone.output.in_features, 1)
                self.classification_branch = nn.Linear(backbone.output.in_features, 5)

            def forward(self, image):
                features = self.backbone(image).flatten(1)
                return self.regression_branch(features), self.classification_branch(features)

        self.model = ComboNet().float().cpu()
        state = torch.load(root / "checkpoint.pth", map_location="cpu", weights_only=True)
        if not isinstance(state, dict) or not state:
            raise ValueError("Expected upstream state dictionary")
        if all(k.startswith("module.") for k in state):
            state = {k[7:]: v for k, v in state.items()}
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        self.transform = transforms.Compose(
            [
                transforms.Resize(224),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def preprocess(self, payload: bytes) -> bytes:
        # Transport verifies bounds. Keep original RGB pixels without JPEG re-encoding.
        return payload

    def predict(self, prepared: bytes) -> float:
        import torch
        from PIL import Image

        with Image.open(BytesIO(prepared)) as image:
            image.load()
            if image.mode != "RGB" or max(image.size) > 4096 or min(image.size) < 224:
                raise ValueError("Expected bounded RGB portrait")
            tensor = self.transform(image).unsqueeze(0)
        with torch.inference_mode():
            regression, _ = self.model(tensor)
        result = float(regression.item())
        if not math.isfinite(result):
            raise ValueError("Non-finite prediction")
        return result

    def normalize(self, raw_score: float) -> float:
        return raw_score  # Native regression scale, no clipping or invented calibration.

    def metadata(self) -> EngineMetadata:
        return EngineMetadata(
            slug="comboloss",
            display_name="ComboLoss / SEResNeXt50",
            version=self.manifest["checkpoint_sha256"],
            licensing_status="reviewed research only",
            provenance=f"https://github.com/lucasxlu/ComboLoss/tree/{SOURCE}",
            commercial_allowed=False,
            research_allowed=True,
            production_enabled=False,
            synthetic=False,
        )
