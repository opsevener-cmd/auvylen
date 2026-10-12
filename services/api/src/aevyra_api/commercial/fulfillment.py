import logging
from typing import Protocol
from uuid import UUID

from aevyra_contracts.commercial import AnalysisStatus, OrderStatus
from aevyra_inference.engine import EngineRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import Analysis, AnalysisResult, Order, now
from aevyra_api.commercial.state import DomainError, transition

logger = logging.getLogger("aevyra.fulfillment")


class Fulfillment(Protocol):
    def fulfill(self, order_id: UUID, *, retry_failed: bool = False) -> None: ...


class SynchronousFulfillment:
    def __init__(
        self, sessions: sessionmaker[Session], registry: EngineRegistry, *, production: bool
    ) -> None:
        self.sessions = sessions
        self.registry = registry
        self.production = production

    def fulfill(self, order_id: UUID, *, retry_failed: bool = False) -> None:
        # Lock the order throughout this short synthetic execution. A worker can replace
        # this service later; Redis is never used as a financial lock/source of truth.
        with self.sessions.begin() as session:
            order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
            if order is None:
                raise DomainError("Order not found", 404)
            if order.status == OrderStatus.COMPLETED:
                return
            if order.status == OrderStatus.FAILED and not retry_failed:
                return
            if order.status not in {OrderStatus.PAID, OrderStatus.FAILED} or order.paid_at is None:
                raise DomainError("Fulfillment requires a confirmed payment")
            analysis = session.scalar(select(Analysis).where(Analysis.order_id == order.id))
            if analysis is None:
                analysis = Analysis(
                    order_id=order.id, scoring_engine_slug="mock", status=AnalysisStatus.CREATED
                )
                session.add(analysis)
                session.flush()
            transition(order, OrderStatus.FULFILLING)
            analysis.status = AnalysisStatus.PROCESSING
            analysis.started_at = now()
            analysis.failure_reason = None
            try:
                score = self.registry.score(
                    analysis.scoring_engine_slug,
                    f"aevyra-development:{order.public_order_id}".encode(),
                    production=self.production,
                )
            except Exception as exc:
                # Commit an explicit failure, retaining the previously committed payment.
                logger.error(
                    "scoring_failed",
                    extra={
                        "order_id": str(order.id),
                        "analysis_id": str(analysis.id),
                        "error_type": type(exc).__name__,
                    },
                )
                analysis.status = AnalysisStatus.FAILED
                analysis.failure_reason = (
                    "Scoring execution failed; explicit operator retry required"
                )
                transition(order, OrderStatus.FAILED)
                return
            session.add(
                AnalysisResult(
                    analysis_id=analysis.id,
                    raw_score=score.raw_score,
                    display_score=score.display_score,
                    engine_slug=score.engine,
                    engine_version=score.version,
                    calibration_version=score.calibration_version,
                    result_metadata={"synthetic": score.synthetic, "scored_at": score.timestamp},
                )
            )
            analysis.status = AnalysisStatus.COMPLETED
            analysis.completed_at = now()
            transition(order, OrderStatus.COMPLETED)
            logger.info(
                "fulfillment_completed",
                extra={"order_id": str(order.id), "analysis_id": str(analysis.id)},
            )
