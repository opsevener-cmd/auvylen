from uuid import UUID

from aevyra_contracts.commercial import EmptyRequest
from aevyra_contracts.research import ResearchJobView
from aevyra_contracts.training import (
    ExtractorView,
    ModelEdit,
    ModelView,
    PredictRequest,
    TrainRequest,
)
from fastapi import APIRouter, Depends, Request

from aevyra_api.preferences.training import ModelService
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions

router = APIRouter(prefix="/api/v1/research/preferences", tags=["personal rating models"])


def service(request: Request) -> ModelService:
    return ModelService(sessions(request), config(request))


@router.get("/extractors", response_model=list[ExtractorView])
def extractors(request: Request, user: CurrentUser) -> list[ExtractorView]:
    return service(request).extractors(user.id)


@router.get("/models", response_model=list[ModelView])
def models(request: Request, user: CurrentUser) -> list[ModelView]:
    return service(request).list(user.id)


@router.post(
    "/train", response_model=ResearchJobView, status_code=202, dependencies=[Depends(csrf)]
)
def train(body: TrainRequest, request: Request, user: CurrentUser) -> ResearchJobView:
    rate(request, "analysis", 30, user.public_user_id)
    return service(request).train(user.id, body)


@router.post(
    "/predict", response_model=ResearchJobView, status_code=202, dependencies=[Depends(csrf)]
)
def predict(body: PredictRequest, request: Request, user: CurrentUser) -> ResearchJobView:
    rate(request, "analysis", 60, user.public_user_id)
    return service(request).predict(user.id, body)


@router.post("/models/{model_id}/edit", response_model=ModelView, dependencies=[Depends(csrf)])
def edit(model_id: UUID, body: ModelEdit, request: Request, user: CurrentUser) -> ModelView:
    return service(request).edit(user.id, model_id, body.archived)


@router.post("/models/{model_id}/delete", dependencies=[Depends(csrf)])
def delete(
    model_id: UUID, body: EmptyRequest, request: Request, user: CurrentUser
) -> dict[str, bool]:
    service(request).delete(user.id, model_id)
    return {"deleted": True}
