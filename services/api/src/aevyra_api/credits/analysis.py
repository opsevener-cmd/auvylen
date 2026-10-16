import logging
from uuid import UUID

from aevyra_inference.engine import EngineRegistry
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import Analysis, AnalysisResult, Product, now
from aevyra_api.commercial.state import DomainError
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import User
from aevyra_api.credits.models import CreditTransaction

logger = logging.getLogger("aevyra.credit_fulfillment")


class CreditAnalysisService:
    """Deduction commits before inference; fulfillment can be invoked by a worker later."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        registry: EngineRegistry,
        *,
        production: bool,
    ) -> None:
        self.sessions = sessions
        self.registry = registry
        self.production = production

    def create(self, user_id: UUID, product_slug: str, request_key: str) -> UUID:
        if self.production:
            raise DomainError("Synthetic analysis is unavailable in production", 404)
        with self.sessions.begin() as session:
            wallet = lock_wallet(session, user_id)
            account = session.get(User, user_id)
            owner = bool(account and account.role == "owner" and account.disabled_at is None)
            existing = session.scalar(
                select(Analysis).where(
                    Analysis.user_id == user_id, Analysis.credit_request_key == request_key
                )
            )
            if existing is not None:
                debit = session.scalar(
                    select(CreditTransaction).where(
                        CreditTransaction.wallet_id == wallet.id,
                        CreditTransaction.idempotency_key == f"analysis:{existing.id}",
                    )
                )
                if owner:
                    if debit is not None:
                        raise DomainError("Analysis request key conflict", 409)
                elif debit is None or debit.transaction_metadata.get("product_slug") != product_slug:
                    raise DomainError("Analysis request key conflict", 409)
                analysis_id = existing.id
            else:
                product = session.scalar(
                    select(Product).where(
                        Product.slug == product_slug,
                        Product.active.is_(True),
                        Product.product_type == "test_analysis",
                    )
                )
                if product is None or product.credit_cost <= 0:
                    raise DomainError("Analysis product unavailable", 404)
                analysis = Analysis(
                    user_id=user_id,
                    order_id=None,
                    credit_request_key=request_key,
                    scoring_engine_slug="mock",
                    status="CREATED",
                )
                session.add(analysis)
                session.flush()
                if not owner:
                    append_credit(
                        session,
                        wallet,
                        amount=-product.credit_cost,
                        kind="ANALYSIS",
                        reference_type="analysis",
                        reference_id=str(analysis.id),
                        key=f"analysis:{analysis.id}",
                        metadata={"product_slug": product.slug},
                    )
                analysis_id = analysis.id
        self.fulfill(analysis_id)
        return analysis_id

    def fulfill(self, analysis_id: UUID) -> None:
        if self.production:
            raise DomainError("Synthetic analysis is unavailable in production", 404)
        with self.sessions.begin() as session:
            analysis = session.scalar(
                select(Analysis)
                .where(Analysis.id == analysis_id, Analysis.user_id.is_not(None))
                .with_for_update()
            )
            if analysis is None or analysis.user_id is None:
                raise DomainError("Analysis not found", 404)
            if analysis.status in {"COMPLETED", "FAILED"}:
                return
            analysis.status = "PROCESSING"
            analysis.started_at = now()
            try:
                score = self.registry.score(
                    analysis.scoring_engine_slug,
                    f"auvylen-credit:{analysis.id}".encode(),
                    production=self.production,
                )
            except Exception as exc:
                logger.error(
                    "credit_scoring_failed",
                    extra={
                        "analysis_id": str(analysis.id),
                        "error_type": type(exc).__name__,
                    },
                )
                analysis.status = "FAILED"
                analysis.failure_reason = "Synthetic analysis failed; Credits refunded"
                analysis.completed_at = now()
                self._refund(session, analysis)
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
            analysis.status = "COMPLETED"
            analysis.completed_at = now()

    def refund_failed(self, analysis_id: UUID) -> None:
        with self.sessions.begin() as session:
            analysis = session.scalar(
                select(Analysis).where(Analysis.id == analysis_id).with_for_update()
            )
            if analysis is None or analysis.user_id is None or analysis.status != "FAILED":
                raise DomainError("Refund requires a failed credit analysis", 409)
            self._refund(session, analysis)

    def _refund(self, session: Session, analysis: Analysis) -> None:
        assert analysis.user_id is not None
        wallet = lock_wallet(session, analysis.user_id)
        debit = session.scalar(
            select(CreditTransaction).where(
                CreditTransaction.wallet_id == wallet.id,
                CreditTransaction.idempotency_key == f"analysis:{analysis.id}",
            )
        )
        if debit is None:
            account = session.get(User, analysis.user_id)
            if account and account.role == "owner":
                return  # Free Owner analysis does not need a refund.
            raise DomainError("Analysis debit missing; reconciliation required", 503)
        if debit.amount >= 0:
            raise DomainError("Analysis debit invalid; reconciliation required", 503)
        append_credit(
            session,
            wallet,
            amount=-debit.amount,
            kind="ANALYSIS_REFUND",
            reference_type="analysis",
            reference_id=str(analysis.id),
            key=f"analysis-refund:{analysis.id}",
        )
