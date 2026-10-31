"""Killable CPU child. Stdout contains only a validated native-scale result."""

import json
import os
import resource
import sys
from pathlib import Path

from aevyra_inference.engine import EngineRegistry

from auvylen_comboloss import Provider

resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
image = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
if len(image) > 10 * 1024 * 1024:
    raise ValueError("Image limit")
engine = Provider().load(Path(sys.argv[1]))
result = EngineRegistry([engine]).score("comboloss", image, production=False, purpose="research")
print(
    json.dumps(
        {
            **result.model_dump(mode="json"),
            "native_scale": [1, 5],
            "calibrated": False,
            "commercial_allowed": False,
        }
    )
)
