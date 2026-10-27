"""Operator-only, CPU-only reproducible export of the reviewed pretrained checkpoint.

Use the isolated export environment documented in docs/pretrained-representation.md.
The website and research worker never download or execute this conversion toolchain.
"""

import argparse
import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

SOURCE = (
    "https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/"
    "mobilenetv3_small_100_lamb-266a294c.pth"
)
SOURCE_SHA = "266a294cbf3d119000a760bf5664a4d80a9674d0616b5cc0836b093d20c38249"
SOURCE_BYTES = 10_256_237
EXPORT_SHA = "164c481657afe9d36e08ff58693df24e511b5bf1a07de9b9389dfc468eedd2a6"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-file", type=Path)
    source.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        if hashlib.sha256(args.output.read_bytes()).hexdigest() != EXPORT_SHA:
            raise SystemExit("Existing export checksum mismatch; refusing overwrite")
        print("Existing export matches reviewed checksum; unchanged.")
        return
    import onnx
    import timm
    import torch
    import torchvision

    if (timm.__version__, torch.__version__, torchvision.__version__, onnx.__version__) != (
        "1.0.30",
        "2.10.0+cpu",
        "0.25.0+cpu",
        "1.22.0",
    ):
        raise SystemExit("Use the exact reviewed CPU export toolchain")
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix=".export-", dir=args.output.parent) as temporary:
        directory = Path(temporary)
        raw = directory / "reviewed-source.pth"
        if args.source_file:
            with args.source_file.open("rb") as file:
                payload = file.read(SOURCE_BYTES + 1)
        else:
            # Honor managed proxy/CA policy, validate TLS, bound the received bytes.
            with urllib.request.urlopen(SOURCE, timeout=60) as response:
                payload = response.read(SOURCE_BYTES + 1)
        if len(payload) != SOURCE_BYTES or hashlib.sha256(payload).hexdigest() != SOURCE_SHA:
            raise SystemExit("Source checkpoint size/checksum mismatch")
        raw.write_bytes(payload)
        os.chmod(raw, 0o600)
        torch.set_num_threads(1)
        model = timm.create_model("mobilenetv3_small_100.lamb_in1k", pretrained=False)
        # Never allow arbitrary Python object deserialization or checkpoint code execution.
        model.load_state_dict(torch.load(raw, map_location="cpu", weights_only=True), strict=True)
        model.reset_classifier(0)
        model.eval()
        tensor = torch.linspace(0, 1, 3 * 224 * 224).reshape(1, 3, 224, 224)
        staged = directory / "embedding.onnx"
        torch.onnx.export(
            model,
            tensor,
            staged,
            input_names=["images"],
            output_names=["embedding"],
            dynamic_axes={"images": {0: "batch"}, "embedding": {0: "batch"}},
            opset_version=17,
            dynamo=False,
            external_data=False,
        )
        onnx.checker.check_model(onnx.load(staged))
        if hashlib.sha256(staged.read_bytes()).hexdigest() != EXPORT_SHA:
            raise SystemExit(
                "Export differs from reviewed graph; do not silently change versions. "
                f"Observed SHA-256: {hashlib.sha256(staged.read_bytes()).hexdigest()}"
            )
        os.chmod(staged, 0o600)
        os.link(staged, args.output)  # Atomic publication; no overwrite.
    print("CPU embedding export verified:", EXPORT_SHA)


if __name__ == "__main__":
    main()
