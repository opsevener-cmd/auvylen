"""Private immutable artifact primitive; never a public file-serving endpoint."""

import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4


class PrivateArtifactStore:
    def __init__(self, root: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def _path(self, owner: UUID, artifact: UUID) -> Path:
        path = self.root / str(owner) / str(artifact)
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise ValueError("Invalid artifact path")
        return path

    def put(self, owner: UUID, payload: bytes) -> tuple[UUID, str]:
        if not payload or len(payload) > self.max_bytes:
            raise ValueError("Artifact size limit")
        artifact = uuid4()
        path = self._path(owner, artifact)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        return artifact, hashlib.sha256(payload).hexdigest()

    def read(self, owner: UUID, artifact: UUID) -> bytes:
        path = self._path(owner, artifact)
        with path.open("rb") as file:
            payload = file.read(self.max_bytes + 1)
        if len(payload) > self.max_bytes:
            raise ValueError("Artifact size limit")
        return payload
