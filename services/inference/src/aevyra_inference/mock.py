import hashlib

from aevyra_contracts import EngineMetadata

from aevyra_inference.engine import ScoringEngine


class MockScoringEngine(ScoringEngine):
    """Synthetic fixture scores. These convey no information about facial aesthetics."""

    def preprocess(self, payload: bytes) -> bytes:
        return payload

    def predict(self, prepared: bytes) -> float:
        digest = hashlib.sha256(prepared).digest()
        return int.from_bytes(digest[:4], "big") / (2**32 - 1)

    def normalize(self, raw_score: float) -> float:
        if not 0 <= raw_score <= 1:
            raise ValueError("Mock raw score must be between zero and one")
        return round(raw_score * 10, 2)

    def metadata(self) -> EngineMetadata:
        return EngineMetadata(
            slug="mock",
            display_name="Mock engine (synthetic development output)",
            version="0.1.0",
            licensing_status="internal-synthetic",
            provenance="Internal deterministic SHA-256 fixture; no model or dataset",
            commercial_allowed=True,
            production_enabled=False,
            synthetic=True,
        )
