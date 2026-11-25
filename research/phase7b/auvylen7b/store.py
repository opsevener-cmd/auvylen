"""Crash-safe, content-addressed storage for a Colab session that can disconnect any time.

Every artifact is written to a temporary name and atomically renamed, so a reconnect
never sees a half-written file. Work units are keyed by a SHA-256 of their full
configuration plus input hashes and code version; an existing key means the unit is done
and is skipped. The run ledger is append-only JSON lines, one record per finished unit.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def key(kind: str, config: dict[str, Any]) -> str:
    return kind + "-" + hashlib.sha256(canonical({"kind": kind, **config})).hexdigest()[:24]


class Store:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger = self.root / "ledger.jsonl"

    def path(self, *parts: str) -> Path:
        target = self.root.joinpath(*parts)
        if self.root.resolve() not in target.resolve().parents:
            raise ValueError("Store paths must stay inside the store root")
        return target

    def write(self, relative: str, payload: bytes) -> Path:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        with temporary.open("wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, target)
        return target

    def exists(self, relative: str) -> bool:
        return self.path(relative).is_file()

    def write_json(self, relative: str, value: Any) -> Path:
        return self.write(
            relative, json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode()
        )

    def read_json(self, relative: str) -> Any:
        return json.loads(self.path(relative).read_bytes())

    def write_arrays(self, relative: str, **arrays: np.ndarray) -> Path:
        buffer = io.BytesIO()
        np.savez(buffer, **arrays)
        return self.write(relative, buffer.getvalue())

    def read_arrays(self, relative: str) -> dict[str, np.ndarray]:
        with np.load(self.path(relative), allow_pickle=False) as data:
            return {name: data[name] for name in data.files}

    def record(self, unit: str, **fields: Any) -> None:
        line = canonical({"unit": unit, "time": time.time(), **fields}) + b"\n"
        with self.ledger.open("ab") as file:
            file.write(line)
            file.flush()
            os.fsync(file.fileno())
