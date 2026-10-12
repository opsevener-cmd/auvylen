from typing import Annotated, cast
from uuid import UUID

from aevyra_contracts.commercial import (
    AnalysisResultView,
    AnalysisView,
    CreateOrderRequest,
    EmptyRequest,
    OrderView,
    PaymentView,
    ProductView,
)
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.events import PaymentEventProcessor
from aevyra_api.commercial.models import Analysis, AnalysisResult
from aevyra_api.commercial.orders import OrderService
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.payments.mock import MockPaymentProvider

router = APIRouter(prefix="/api/v1", tags=["development commercial flow"])


def development_only(request: Request) -> None:
    config = cast(Settings, request.app.state.settings)
    if (
        config.api_environment == "production"
        or config.public_pilot
        or not config.mock_checkout_enabled
    ):
        raise DomainError("Commercial development routes are unavailable", 404)


router.dependencies = [Depends(development_only)]


def orders(request: Request) -> OrderService:
    return cast(OrderService, request.app.state.orders)


Orders = Annotated[OrderService, Depends(orders)]
EmptyBody = Annotated[EmptyRequest, Body()]


@router.get("/products", response_model=list[ProductView])
def products(service: Orders) -> list[ProductView]:
    return service.products()


@router.post("/orders", response_model=OrderView, status_code=201)
def create_order(body: CreateOrderRequest, service: Orders) -> OrderView:
    return service.create(body.product_slug)


@router.get("/orders/{public_order_id}", response_model=OrderView)
def get_order(public_order_id: str, service: Orders) -> OrderView:
    return service.get(public_order_id)


@router.post("/orders/{public_order_id}/payments", response_model=PaymentView)
def create_payment(public_order_id: str, body: EmptyBody, service: Orders) -> PaymentView:
    return service.create_payment(public_order_id)


@router.post("/dev/payments/{payment_id}/simulate-success", response_model=OrderView)
def simulate_success(
    payment_id: UUID, body: EmptyBody, request: Request, service: Orders
) -> OrderView:
    provider = cast(MockPaymentProvider, request.app.state.mock_provider)
    processor = cast(PaymentEventProcessor, request.app.state.payment_events)
    public_id = processor.process(provider.success_event(service.payment_details(payment_id)))
    return service.get(public_id)


@router.get("/analyses/{analysis_id}", response_model=AnalysisView)
def get_analysis(analysis_id: UUID, request: Request) -> AnalysisView:
    sessions = cast(sessionmaker[Session], request.app.state.sessions)
    with sessions() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None or analysis.order_id is None:
            raise DomainError("Analysis not found", 404)
        return AnalysisView.model_validate(analysis)


@router.get("/analyses/{analysis_id}/result", response_model=AnalysisResultView)
def get_result(analysis_id: UUID, request: Request) -> AnalysisResultView:
    sessions = cast(sessionmaker[Session], request.app.state.sessions)
    with sessions() as session:
        result = session.scalar(
            select(AnalysisResult)
            .join(Analysis)
            .where(AnalysisResult.analysis_id == analysis_id, Analysis.order_id.is_not(None))
        )
        if result is None:
            raise DomainError("Analysis result not available", 404)
        return AnalysisResultView(
            analysis_id=result.analysis_id,
            raw_score=result.raw_score,
            display_score=result.display_score,
            engine_slug=result.engine_slug,
            engine_version=result.engine_version,
            calibration_version=result.calibration_version,
            metadata=result.result_metadata,
            created_at=result.created_at,
        )
