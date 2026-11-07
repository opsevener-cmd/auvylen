"""Dev-only: embed development images (sealed test already excluded) with timm weights.

Run in a separate PyTorch environment, never the application's. Checkpoints come from the
pinned timm configurations' GitHub release URLs and are checked against the hash prefix in
their filenames. Requires the project inference package in the isolated research environment.
Usage: python -I embed.py IMAGES_DIR PRIVATE_STUDY_DIR SUBJECT_REGISTRY_JSON
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import timm
import torch
from aevyra_inference.native_dev_study import checked_development_rows
from PIL import Image

root, out, registry = (Path(v) for v in sys.argv[1:4])
rows = checked_development_rows(out / "development.csv", registry)
names = json.load(open(out / "development-images.json"))
if names != [r["image"] for r in rows]:
    raise ValueError("Embedding inventory must match the checked development table")
models = [
    "mobilenetv3_small_100.lamb_in1k",
    "mobilenetv3_large_100.ra_in1k",
    "efficientnet_b0.ra_in1k",
    "efficientnet_b3.ra2_in1k",
    "convnext_nano.d1h_in1k",
]
torch.set_num_threads(4)
record = {}
for name in models:
    cfg = timm.models.get_pretrained_cfg(name).to_dict()
    url = cfg["url"]
    file = out / url.split("/")[-1]
    if not file.exists():
        urllib.request.urlretrieve(url, file)
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    prefix = url.split("-")[-1].split(".")[0]
    assert digest.startswith(prefix), (name, "checkpoint hash mismatch")
    model = timm.create_model(
        name, pretrained=True, num_classes=0, pretrained_cfg_overlay=dict(file=str(file))
    ).eval()
    data = timm.data.resolve_data_config({}, model=model)
    tf = timm.data.create_transform(**data)
    feats = {}
    with torch.inference_mode():
        for view in ("clean", "mirror", "lighting", "crop"):
            batch = []
            for n in names:
                im = Image.open(root / n).convert("RGB")
                if view == "mirror":
                    im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                if view == "lighting":
                    from PIL import ImageEnhance

                    im = ImageEnhance.Brightness(im).enhance(0.85)
                if view == "crop":
                    w, h = im.size
                    im = im.crop(
                        (round(w * 0.05), round(h * 0.05), round(w * 0.95), round(h * 0.95))
                    )
                batch.append(tf(im))
            feats[view] = torch.cat(
                [model(torch.stack(batch[i : i + 16])) for i in range(0, len(batch), 16)]
            ).numpy()
    np.savez(out / f"{name}.npz", **feats)
    record[name] = {
        "license": cfg.get("license"),
        "sha256": digest,
        "dim": int(feats["clean"].shape[1]),
        "params_m": round(sum(p.numel() for p in model.parameters()) / 1e6, 2),
        "input": data["input_size"],
    }
    print(name, record[name], flush=True)
json.dump(record, open(out / "encoders.json", "w"), indent=2)
