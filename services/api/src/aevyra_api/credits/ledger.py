from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aevyra_api.commercial.state import DomainError
from aevyra_api.credits.models import CreditTransaction, Wallet


def lock_wallet(session: Session, user_id: UUID) -> Wallet:
    wallet = session.scalar(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    if wallet is None:
        raise DomainError("Wallet not found", 404)
    return wallet


def append_credit(
    session: Session,
    wallet: Wallet,
    *,
    amount: int,
    kind: str,
    reference_type: str,
    reference_id: str,
    key: str,
    reason: str = "",
    metadata: dict[str, JsonValue] | None = None,
) -> CreditTransaction:
    """Caller must hold the wallet row lock until commit. History is authoritative."""
    existing = session.scalar(
        select(CreditTransaction).where(
            CreditTransaction.wallet_id == wallet.id, CreditTransaction.idempotency_key == key
        )
    )
    if existing is not None:
        if (
            existing.amount,
            existing.transaction_type,
            existing.reference_type,
            existing.reference_id,
        ) != (
            amount,
            kind,
            reference_type,
            reference_id,
        ):
            raise DomainError("Idempotency key conflicts with an earlier operation", 409)
        return existing
    balance = session.scalar(
        select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
            CreditTransaction.wallet_id == wallet.id
        )
    )
    if balance != wallet.cached_balance:
        raise DomainError("Wallet reconciliation required", 503)
    if amount == 0:
        raise DomainError("Credit amount must be nonzero", 422)
    next_balance = wallet.cached_balance + amount
    if next_balance < 0:
        raise DomainError("Insufficient Credits", 409)
    if next_balance > 9_007_199_254_740_991:
        raise DomainError("Credit balance limit exceeded", 409)
    entry = CreditTransaction(
        wallet_id=wallet.id,
        amount=amount,
        transaction_type=kind,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=key,
        balance_after=next_balance,
        transaction_metadata=metadata or ({"reason": reason} if reason else {}),
    )
    wallet.cached_balance = next_balance
    session.add(entry)
    session.flush()
    return entry
