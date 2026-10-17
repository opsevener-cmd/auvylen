"""Local operator commands. No public generation or wallet-mutation endpoints."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from aevyra_api.accounts import pepper
from aevyra_api.admin_models import AdminAudit
from aevyra_api.administration import audit
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.codes import generate_batch
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import (
    CreditTransaction,
    RedemptionBatch,
    RedemptionCode,
    User,
    Wallet,
)
from aevyra_api.database import DependencyChecks
from aevyra_api.routes.scoring import registry


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Auvylen audited operator CLI")
    commands = root.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-batch")
    generate.add_argument("--name", required=True)
    generate.add_argument("--channel", required=True)
    generate.add_argument("--sku", required=True)
    generate.add_argument("--credits", type=int, required=True)
    generate.add_argument("--quantity", type=int, required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--expires-at", type=datetime.fromisoformat)
    for verb in ("batch-summary", "disable-batch", "expire-batch"):
        sub = commands.add_parser(verb)
        sub.add_argument("public_batch_id")
    commands.add_parser("wallet").add_argument("public_user_id")
    for verb in ("grant", "compensate"):
        sub = commands.add_parser(verb)
        sub.add_argument("public_user_id")
        sub.add_argument("--amount", type=int, required=True)
        sub.add_argument("--reason", required=True)
        sub.add_argument("--key", type=UUID, required=True)
    for verb in ("resume-analysis", "refund-failed-analysis"):
        commands.add_parser(verb).add_argument("analysis_id", type=UUID)
    return root


def main() -> int:
    args = parser().parse_args()
    checks: DependencyChecks | None = None
    try:
        settings = Settings()
        checks = DependencyChecks(settings)
        sessions = checks.sessions
        if args.command == "generate-batch":
            batch_id = generate_batch(
                sessions,
                pepper(settings),
                name=args.name,
                channel=args.channel,
                sku=args.sku,
                credits=args.credits,
                quantity=args.quantity,
                output=args.output,
                expires_at=args.expires_at,
                audit_terminal=True,
            )
            print(
                json.dumps(
                    {
                        "batch": batch_id,
                        "quantity": args.quantity,
                        "export": str(args.output),
                        "warning": "Protect this plaintext-code export",
                    }
                )
            )
        elif args.command in {"batch-summary", "disable-batch", "expire-batch"}:
            with sessions.begin() as session:
                batch = session.scalar(
                    select(RedemptionBatch)
                    .where(RedemptionBatch.public_batch_id == args.public_batch_id)
                    .with_for_update()
                )
                if batch is None:
                    raise DomainError("Batch not found", 404)
                if args.command == "disable-batch":
                    batch.active = False
                elif args.command == "expire-batch":
                    batch.expires_at = now()
                if args.command != "batch-summary":
                    audit(
                        session,
                        None,
                        "terminal." + args.command,
                        batch.public_batch_id,
                        details={"control": "deployment-terminal"},
                    )
                redeemed = session.scalar(
                    select(func.count())
                    .select_from(RedemptionCode)
                    .where(RedemptionCode.batch_id == batch.id, RedemptionCode.status == "REDEEMED")
                )
                print(
                    json.dumps(
                        {
                            "batch": batch.public_batch_id,
                            "channel": batch.channel,
                            "quantity": batch.quantity,
                            "redeemed": redeemed,
                            "active": batch.active,
                            "expires_at": batch.expires_at.isoformat()
                            if batch.expires_at
                            else None,
                        }
                    )
                )
        elif args.command in {"resume-analysis", "refund-failed-analysis"}:
            service = CreditAnalysisService(
                sessions, registry, production=settings.api_environment == "production"
            )
            if args.command == "resume-analysis":
                service.fulfill(args.analysis_id)
            else:
                service.refund_failed(args.analysis_id)
            with sessions.begin() as session:
                audit(
                    session,
                    None,
                    "terminal." + args.command,
                    str(args.analysis_id),
                    details={"control": "deployment-terminal"},
                )
            print(json.dumps({"analysis": str(args.analysis_id), "operation": args.command}))
        else:
            with sessions.begin() as session:
                user = session.scalar(
                    select(User).where(User.public_user_id == args.public_user_id)
                )
                if user is None:
                    raise DomainError("User not found", 404)
                wallet: Wallet = lock_wallet(session, user.id)
                if args.command != "wallet":
                    if not 1 <= abs(args.amount) <= 1_000_000 or not 1 <= len(args.reason) <= 500:
                        raise DomainError("Amount/reason outside operator limits", 422)
                    if args.command == "grant" and args.amount < 0:
                        raise DomainError("Promotional grant must be positive", 422)
                    append_credit(
                        session,
                        wallet,
                        amount=args.amount,
                        kind="PROMOTION" if args.command == "grant" else "MANUAL_COMPENSATION",
                        reference_type="operator",
                        reference_id=str(args.key),
                        key=f"operator:{args.key}",
                        reason=args.reason,
                    )
                    audit_key = f"operator:{args.key}"
                    if not session.scalar(
                        select(AdminAudit).where(AdminAudit.request_key == audit_key)
                    ):
                        session.add(
                            AdminAudit(
                                actor_id=None,
                                action="terminal." + args.command,
                                target=user.public_user_id,
                                outcome="success",
                                request_key=audit_key,
                                details={
                                    "control": "deployment-terminal",
                                    "reason": args.reason,
                                    "amount": args.amount,
                                },
                            )
                        )
                balance = session.scalar(
                    select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                        CreditTransaction.wallet_id == wallet.id
                    )
                )
                print(
                    json.dumps(
                        {
                            "user": user.public_user_id,
                            "balance": balance,
                            "cached_balance": wallet.cached_balance,
                            "consistent": balance == wallet.cached_balance,
                        }
                    )
                )
        return 0
    except Exception as exc:
        # Never print exception messages/parameters that might contain codes or credentials.
        print(
            f"Operator command failed ({type(exc).__name__}); review configuration/arguments",
            file=sys.stderr,
        )
        return 1
    finally:
        if checks is not None:
            checks.close()


if __name__ == "__main__":
    raise SystemExit(main())
