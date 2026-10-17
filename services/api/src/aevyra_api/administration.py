"""Transactional Owner mutations reusing the existing ledger and redemption primitives."""

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta
from uuid import UUID, uuid4

from aevyra_contracts.owner import (
    AdminCommand,
    BatchCreateCommand,
    CreditGrantCommand,
    ResearchAccessCommand,
    UserStatusCommand,
)
from pydantic import JsonValue
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.accounts import session_digest
from aevyra_api.admin_models import AdminAudit
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.codes import aware, digest_code, generate_code
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import AccountSession, RedemptionBatch, RedemptionCode, User
from aevyra_api.entitlements import require_owner
from aevyra_api.research.models import ResearchAccess, ResearchJob


def audit(
    session: Session,
    actor: UUID | None,
    action: str,
    target: str,
    *,
    outcome: str = "success",
    details: dict[str, JsonValue] | None = None,
) -> None:
    session.add(
        AdminAudit(
            actor_id=actor, action=action, target=target, outcome=outcome, details=details or {}
        )
    )


class Administration:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions = sessions
        self.settings = settings

    def mutate(
        self,
        actor: UUID,
        token: str,
        action: str,
        target: str,
        body: AdminCommand,
        operation: Callable[[Session], dict[str, JsonValue]],
        *,
        secrets_once: bool = False,
    ) -> dict[str, JsonValue]:
        fingerprint = hashlib.sha256(
            json.dumps(
                {"action": action, "target": target, "body": body.model_dump(mode="json")},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.sessions.begin() as session:
            # Serialize administration + credential rotation, then revalidate session.
            user = session.scalar(select(User).where(User.id == actor).with_for_update())
            require_owner(user)
            auth = session.scalar(
                select(AccountSession).where(
                    AccountSession.user_id == actor,
                    AccountSession.token_digest == session_digest(token),
                )
            )
            if auth is None or aware(auth.expires_at) <= now():
                raise DomainError("Sign in required", 401)
            if aware(auth.created_at) < now() - timedelta(
                seconds=self.settings.owner_fresh_auth_seconds
            ):
                raise DomainError("Fresh Owner sign-in required for this operation", 403)
            previous = session.scalar(
                select(AdminAudit).where(AdminAudit.request_key == str(body.idempotency_key))
            )
            if previous:
                if previous.fingerprint != fingerprint:
                    raise DomainError("Administrative request key conflict", 409)
                if secrets_once:
                    raise DomainError(
                        "Batch already created; codes cannot be exported again."
                        " Review batches before retrying.",
                        409,
                    )
                result = previous.details.get("result")
                assert isinstance(result, dict)
                return result
            result = operation(session)
            safe_result = {k: v for k, v in result.items() if k != "codes"}
            session.add(
                AdminAudit(
                    actor_id=actor,
                    action=action,
                    target=target,
                    outcome="success",
                    request_key=str(body.idempotency_key),
                    fingerprint=fingerprint,
                    details={"reason": body.reason, "result": safe_result},
                )
            )
            return result

    @staticmethod
    def standard_user(session: Session, public_id: str) -> User:
        target = session.scalar(
            select(User).where(User.public_user_id == public_id).with_for_update()
        )
        if target is None:
            raise DomainError("User not found", 404)
        if target.role != "user":
            raise DomainError("Owner identity cannot be changed through administration", 403)
        return target

    @staticmethod
    def cancel_work(session: Session, user_id: UUID) -> None:
        for job in session.scalars(
            select(ResearchJob)
            .where(ResearchJob.user_id == user_id, ResearchJob.status.in_(["QUEUED", "RUNNING"]))
            .with_for_update()
        ):
            job.status = "FAILED"
            job.failure_reason = "Research authorization revoked by administrator"
            job.phase = "Cancelled"
            job.completed_at = now()
            job.lease_token = None
            job.lease_until = None
            job.result = None

    def user_status(
        self, session: Session, target: str, body: UserStatusCommand
    ) -> dict[str, JsonValue]:
        user = self.standard_user(session, target)
        user.disabled_at = now() if body.disabled else None
        if body.disabled:
            session.execute(delete(AccountSession).where(AccountSession.user_id == user.id))
            self.cancel_work(session, user.id)
        return {"public_user_id": target, "disabled": body.disabled}

    def research_access(
        self, session: Session, target: str, body: ResearchAccessCommand
    ) -> dict[str, JsonValue]:
        user = self.standard_user(session, target)
        access = session.get(ResearchAccess, user.id)
        if access is None:
            session.add(ResearchAccess(user_id=user.id, enabled=body.enabled, reason=body.reason))
        else:
            access.enabled, access.reason = body.enabled, body.reason
        if not body.enabled:
            self.cancel_work(session, user.id)
        return {"public_user_id": target, "research_enabled": body.enabled}

    def grant(
        self, session: Session, actor: UUID, target: str, body: CreditGrantCommand
    ) -> dict[str, JsonValue]:
        user = self.standard_user(session, target)
        wallet = lock_wallet(session, user.id)
        entry = append_credit(
            session,
            wallet,
            amount=body.amount,
            kind="PROMOTION",
            reference_type="owner_promotion",
            reference_id=str(body.idempotency_key),
            key=f"owner:{body.idempotency_key}",
            metadata={"actor_id": str(actor), "reason": body.reason},
        )
        return {
            "transaction_id": str(entry.id),
            "balance": wallet.cached_balance,
            "amount": entry.amount,
        }

    @staticmethod
    def batch(session: Session, pepper: str, body: BatchCreateCommand) -> dict[str, JsonValue]:
        batch = RedemptionBatch(
            public_batch_id="batch_" + uuid4().hex,
            name=body.name,
            channel=body.channel,
            sku=body.sku,
            credits_per_code=body.credits,
            quantity=body.quantity,
            expires_at=now() + timedelta(days=body.expires_days),
            active=True,
        )
        session.add(batch)
        session.flush()
        codes: list[JsonValue] = []
        for _ in range(body.quantity):
            code = generate_code()
            session.add(
                RedemptionCode(
                    batch_id=batch.id,
                    lookup_digest=digest_code(code, pepper),
                    masked_suffix=code[-4:],
                    expires_at=batch.expires_at,
                )
            )
            codes.append(code)
        return {"public_batch_id": batch.public_batch_id, "quantity": body.quantity, "codes": codes}

    @staticmethod
    def disable_batch(session: Session, target: str) -> dict[str, JsonValue]:
        batch = session.scalar(
            select(RedemptionBatch)
            .where(RedemptionBatch.public_batch_id == target)
            .with_for_update()
        )
        if batch is None:
            raise DomainError("Batch not found", 404)
        batch.active = False
        return {"public_batch_id": target, "active": False}
