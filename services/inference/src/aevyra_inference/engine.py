from abc import ABC, abstractmethod
from datetime import UTC, datetime

from aevyra_contracts import EngineMetadata, ScoringResult


class ScoringEngine(ABC):
    """Opaque bytes keep transport/image libraries out of the common interface."""

    @abstractmethod
    def preprocess(self, payload: bytes) -> bytes: ...

    @abstractmethod
    def predict(self, prepared: bytes) -> float: ...

    @abstractmethod
    def normalize(self, raw_score: float) -> float: ...

    @abstractmethod
    def metadata(self) -> EngineMetadata: ...


class EnginePolicyError(RuntimeError):
    pass


class EngineRegistry:
    def __init__(self, engines: list[ScoringEngine]) -> None:
        self._engines: dict[str, ScoringEngine] = {}
        for engine in engines:
            slug = engine.metadata().slug
            if slug in self._engines:
                raise ValueError(f"Duplicate engine slug: {slug}")
            self._engines[slug] = engine

    def metadata(self) -> list[EngineMetadata]:
        return [engine.metadata() for engine in self._engines.values()]

    def score(self, slug: str, payload: bytes, *, production: bool) -> ScoringResult:
        engine = self._engines[slug]
        info = engine.metadata()
        # Policy runs before any preprocessing or inference.
        if production and (not info.commercial_allowed or not info.production_enabled):
            raise EnginePolicyError("Engine is not approved for production execution")
        raw = engine.predict(engine.preprocess(payload))
        return ScoringResult(
            raw_score=raw,
            display_score=engine.normalize(raw),
            engine=info.slug,
            version=info.version,
            timestamp=datetime.now(UTC).isoformat(),
            synthetic=info.synthetic,
        )
