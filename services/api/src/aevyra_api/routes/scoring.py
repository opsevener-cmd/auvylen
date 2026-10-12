from aevyra_contracts import EngineListResponse
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.mock import MockScoringEngine
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["scoring engines"])
registry = EngineRegistry([MockScoringEngine()])


@router.get("/scoring-engines", response_model=EngineListResponse)
def scoring_engines() -> EngineListResponse:
    return EngineListResponse(engines=registry.metadata())
