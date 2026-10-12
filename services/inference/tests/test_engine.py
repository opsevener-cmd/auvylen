from datetime import datetime

import pytest
from aevyra_inference.engine import EnginePolicyError, EngineRegistry
from aevyra_inference.mock import MockScoringEngine


def test_deterministic_mock() -> None:
    engine = MockScoringEngine()
    prepared = engine.preprocess(b"synthetic fixture")
    assert engine.predict(prepared) == engine.predict(prepared)
    assert engine.predict(prepared) != engine.predict(b"other fixture")
    assert 0 <= engine.predict(prepared) <= 1
    assert engine.normalize(0.73) == 7.3
    with pytest.raises(ValueError):
        engine.normalize(2)


def test_registry_records_provenance() -> None:
    registry = EngineRegistry([MockScoringEngine()])
    result = registry.score("mock", b"test", production=False)
    repeated = registry.score("mock", b"test", production=False)
    assert result.raw_score == repeated.raw_score
    assert result.display_score == repeated.display_score
    assert result.synthetic is True
    assert result.version == "0.1.0"
    assert datetime.fromisoformat(result.timestamp).tzinfo is not None
    assert registry.metadata()[0].commercial_allowed is True
    with pytest.raises(KeyError):
        registry.score("missing", b"test", production=False)
    with pytest.raises(ValueError, match="Duplicate"):
        EngineRegistry([MockScoringEngine(), MockScoringEngine()])


@pytest.mark.parametrize("commercial,enabled", [(True, False), (False, True), (False, False)])
def test_production_gate_precedes_execution(commercial: bool, enabled: bool) -> None:
    class RestrictedEngine(MockScoringEngine):
        def metadata(self):
            return (
                super()
                .metadata()
                .model_copy(
                    update={"commercial_allowed": commercial, "production_enabled": enabled}
                )
            )

        def preprocess(self, payload: bytes) -> bytes:
            raise AssertionError("Policy must reject before preprocessing")

    registry = EngineRegistry([RestrictedEngine()])
    with pytest.raises(EnginePolicyError):
        registry.score("mock", b"test", production=True)
