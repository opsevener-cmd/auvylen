import csv
import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.admin_models import AdminAudit
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import Redemption, RedemptionBatch, RedemptionCode

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
INVALID = "Code is invalid, expired or already used"


def normalize_code(value: str) -> str:
    value = value.strip().upper()
    # Accept exactly the published grouping or its unhyphenated equivalent.
    pattern = f"AUV-(?:[{ALPHABET}]{{4}}-){{5}}[{ALPHABET}]{{4}}"
    compact = f"AUV[{ALPHABET}]{{24}}"
    if len(value) > 40 or not (re.fullmatch(pattern, value) or re.fullmatch(compact, value)):
        raise DomainError(INVALID, 400)
    return value.replace("-", "")


def digest_code(value: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), normalize_code(value).encode(), hashlib.sha256).hexdigest()


def generate_code() -> str:
    # 24 independent symbols (~118 bits); never random.Random or sequential identifiers.
    random_part = "".join(secrets.choice(ALPHABET) for _ in range(24))
    return "AUV-" + "-".join(random_part[i : i + 4] for i in range(0, 24, 4))


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def generate_batch(
    sessions: sessionmaker[Session],
    pepper: str,
    *,
    name: str,
    channel: str,
    sku: str,
    credits: int,
    quantity: int,
    output: Path,
    expires_at: datetime | None = None,
    audit_terminal: bool = False,
) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", channel):
        raise DomainError("Channel must be a lowercase identifier", 422)
    if not 1 <= credits <= 1_000_000 or not 1 <= quantity <= 100_000:
        raise DomainError("Credits/quantity outside operator limits", 422)
    if not 1 <= len(name) <= 200 or not 1 <= len(sku) <= 100:
        raise DomainError("Name/sku outside operator limits", 422)
    if any(text.startswith(("=", "+", "-", "@", "\t", "\r")) for text in (name, sku)):
        raise DomainError("Spreadsheet formula prefixes are not allowed", 422)
    if expires_at is not None and aware(expires_at) <= now():
        raise DomainError("Expiration must be in the future", 422)
    output = output.resolve()
    # Sensitive output is explicitly restricted to the gitignored export directory.
    root = Path.cwd().resolve() / "exports"
    if root not in output.parents or output.suffix.lower() != ".csv":
        raise DomainError("Export must be a .csv file inside ./exports", 422)
    output.parent.mkdir(parents=True, exist_ok=True)
    public_id = "batch_" + uuid4().hex
    # O_EXCL prevents overwrites. The batch is inactive until CSV writing finishes.
    # On rollback the partial file is removed; a crash can leave a partial file with
    # no committed batch. Operators must inspect its batch ID before delivering codes.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as export:
            with sessions.begin() as session:
                batch = RedemptionBatch(
                    public_batch_id=public_id,
                    name=name,
                    channel=channel,
                    sku=sku,
                    credits_per_code=credits,
                    quantity=quantity,
                    expires_at=expires_at,
                    active=False,
                )
                session.add(batch)
                session.flush()
                writer = csv.DictWriter(
                    export, fieldnames=["code", "credits", "batch", "channel", "expires_at"]
                )
                writer.writeheader()
                seen: set[str] = set()
                for _ in range(quantity):
                    code = generate_code()
                    digest = digest_code(code, pepper)
                    while digest in seen:
                        code = generate_code()
                        digest = digest_code(code, pepper)
                    seen.add(digest)
                    session.add(
                        RedemptionCode(
                            batch_id=batch.id,
                            lookup_digest=digest,
                            masked_suffix=code[-4:],
                            expires_at=expires_at,
                        )
                    )
                    writer.writerow(
                        {
                            "code": code,
                            "credits": credits,
                            "batch": public_id,
                            "channel": channel,
                            "expires_at": expires_at.isoformat() if expires_at else "",
                        }
                    )
                export.flush()
                os.fsync(export.fileno())
                batch.active = True
                if audit_terminal:
                    session.add(
                        AdminAudit(
                            actor_id=None,
                            action="terminal.batch.create",
                            target=public_id,
                            outcome="success",
                            details={
                                "control": "deployment-terminal",
                                "quantity": quantity,
                                "credits_per_code": credits,
                            },
                        )
                    )
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return public_id


def redeem(
    sessions: sessionmaker[Session],
    pepper: str,
    user_id: UUID,
    value: str,
) -> tuple[int, int]:
    digest = digest_code(value, pepper)
    with sessions.begin() as session:
        found = session.scalar(select(RedemptionCode).where(RedemptionCode.lookup_digest == digest))
        if found is None:
            raise DomainError(INVALID, 400)
        # Shared batch lock allows different codes concurrently, but blocks batch disable.
        batch = session.scalar(
            select(RedemptionBatch)
            .where(RedemptionBatch.id == found.batch_id)
            .with_for_update(read=True)
        )
        code = session.scalar(
            select(RedemptionCode)
            .where(RedemptionCode.id == found.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            batch is None
            or not batch.active
            or code is None
            or code.status != "AVAILABLE"
            or (batch.expires_at is not None and aware(batch.expires_at) <= now())
            or (code.expires_at is not None and aware(code.expires_at) <= now())
        ):
            raise DomainError(INVALID, 400)
        wallet = lock_wallet(session, user_id)
        # A wallet lock may have waited; expiry must still be valid at credit decision.
        if (batch.expires_at is not None and aware(batch.expires_at) <= now()) or (
            code.expires_at is not None and aware(code.expires_at) <= now()
        ):
            raise DomainError(INVALID, 400)
        entry = append_credit(
            session,
            wallet,
            amount=batch.credits_per_code,
            kind="REDEMPTION",
            reference_type="redemption_code",
            reference_id=str(code.id),
            key=f"redemption:{code.id}",
        )
        code.status = "REDEEMED"
        session.add(
            Redemption(
                redemption_code_id=code.id,
                user_id=user_id,
                wallet_id=wallet.id,
                credit_transaction_id=entry.id,
                source_metadata={
                    "batch": batch.public_batch_id,
                    "channel": batch.channel,
                    "sku": batch.sku,
                },
            )
        )
        return batch.credits_per_code, wallet.cached_balance
