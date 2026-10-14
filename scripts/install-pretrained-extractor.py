"""Operator-only installation of reviewed weights; never invoked by HTTP or workers.

Run on the approved Linux cloud host. No personal photographs are downloaded.
"""

import argparse
import os
import tempfile
from pathlib import Path

from aevyra_inference.extractors import WEIGHT_BYTES, WEIGHT_FILE, verified_weights

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, required=True, help="PRIVATE_MODEL_ROOT/pretrained")
parser.add_argument(
    "--source-file", type=Path, required=True, help="Verified exported embedding ONNX file"
)
args = parser.parse_args()
args.root.mkdir(parents=True, exist_ok=True, mode=0o700)
for notice in ("LICENSE", "NOTICE"):
    source_notice = (
        Path(__file__).resolve().parents[1] / f"docs/licenses/mobilenetv3-small-{notice}.txt"
    )
    destination = args.root / f"mobilenetv3-small-{notice}.txt"
    if not destination.exists():
        with destination.open("xb") as file:
            file.write(source_notice.read_bytes())
        os.chmod(destination, 0o600)
target = args.root / WEIGHT_FILE
if target.exists():
    verified_weights(args.root)
    print("Existing checkpoint verified; no overwrite.")
else:
    with tempfile.TemporaryDirectory(prefix=".install-", dir=args.root) as temporary:
        staged = Path(temporary) / WEIGHT_FILE
        with staged.open("xb") as output:
            os.chmod(staged, 0o600)
            with args.source_file.open("rb") as file:
                output.write(file.read(WEIGHT_BYTES + 1))
            output.flush()
            os.fsync(output.fileno())
        verified_weights(Path(temporary))
        # Link atomically and refuse to overwrite a concurrently installed artifact.
        os.link(staged, target)
    print("Reviewed MobileNetV3-Small checkpoint installed and SHA-256 verified.")
