"""Explicit terminal-only provisioning/recovery with the deployment's database credentials."""

import argparse
import getpass
import os
import secrets
import sys
from uuid import uuid4

from argon2.exceptions import VerificationError
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.accounts import HASHER
from aevyra_api.administration import audit
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import AccountSession, User, Wallet
from aevyra_api.database import DependencyChecks
from aevyra_api.entitlements import OWNER_LOGIN, require_owner
from aevyra_api.research.models import ResearchAccess


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise ValueError("Owner password length must be 12–128 characters")


def provision(sessions: sessionmaker[Session], password: str) -> str:
    """The partial unique index is the final concurrent-bootstrap guard."""
    validate_password(password)
    hashed = HASHER.hash(password)
    try:
        with sessions.begin() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                session.execute(text("SELECT pg_advisory_xact_lock(518927407)"))
            if session.scalar(select(User).where(User.role == "owner")):
                raise ValueError("Owner account already exists; password unchanged")
            if session.scalar(select(User).where(User.login_identifier == OWNER_LOGIN)):
                raise ValueError("Reserved Owner login is occupied; manual review required")
            user = User(
                public_user_id="usr_" + uuid4().hex,
                login_identifier=OWNER_LOGIN,
                password_hash=hashed,
                role="owner",
            )
            session.add(user)
            session.flush()
            session.add(Wallet(user_id=user.id))
            session.add(
                ResearchAccess(user_id=user.id, enabled=True, reason="Private terminal bootstrap")
            )
            audit(
                session,
                user.id,
                "owner.provision",
                user.public_user_id,
                details={"control": "deployment-terminal"},
            )
    except IntegrityError:
        raise ValueError("Owner identity already exists; no credentials changed") from None
    return OWNER_LOGIN


def rotate(
    sessions: sessionmaker[Session],
    password: str,
    *,
    current_password: str | None = None,
    recovery_confirmation: str | None = None,
) -> None:
    validate_password(password)
    with sessions.begin() as session:
        user = session.scalar(select(User).where(User.role == "owner").with_for_update())
        require_owner(user)
        assert user is not None
        if current_password is not None:
            try:
                HASHER.verify(user.password_hash, current_password)
            except VerificationError:
                raise ValueError("Current password is incorrect") from None
        elif recovery_confirmation != f"RECOVER {user.public_user_id}":
            raise ValueError(
                "Recovery requires explicit confirmation of the existing Owner identity"
            )
        same: bool
        try:
            same = HASHER.verify(user.password_hash, password)
        except VerificationError:
            same = False
        if same:
            raise ValueError("Choose a different new password")
        user.password_hash = HASHER.hash(password)
        session.execute(delete(AccountSession).where(AccountSession.user_id == user.id))
        audit(
            session,
            user.id,
            "owner.rotate" if current_password is not None else "owner.recover",
            user.public_user_id,
            details={"sessions_revoked": True, "control": "deployment-terminal"},
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "rotate", "recover"], nargs="?", default="init")
    args = parser.parse_args()
    if not sys.stdin.isatty() or not sys.stderr.isatty() or not sys.stdout.isatty():
        raise SystemExit("Owner management requires an interactive private terminal, never a pipe")
    if os.environ.get("CODESPACES") != "true" or not os.environ.get("CODESPACE_NAME"):
        raise SystemExit(
            "Use the private Codespace terminal with its existing database credentials"
        )
    checks = DependencyChecks(Settings())
    try:
        try:
            current = None
            confirmation = None
            if args.action == "rotate":
                current = getpass.getpass("Current Owner password: ")
            elif args.action == "recover":
                with checks.sessions() as session:
                    user = session.scalar(select(User).where(User.role == "owner"))
                    if user is None:
                        raise ValueError("No Owner exists; use owner-init")
                    confirmation = input(
                        "Terminal recovery revokes all sessions. "
                        f"Type RECOVER {user.public_user_id}: "
                    )
            first = getpass.getpass(
                "New Owner password (never reuse a password disclosed in chat): "
            )
            second = getpass.getpass("Confirm new Owner password: ")
            if not secrets.compare_digest(first.encode(), second.encode()):
                raise ValueError("Passwords do not match; nothing changed")
            if args.action == "init":
                provision(checks.sessions, first)
            else:
                rotate(
                    checks.sessions,
                    first,
                    current_password=current,
                    recovery_confirmation=confirmation,
                )
        except (ValueError, DomainError) as exc:
            with checks.sessions.begin() as session:
                audit(
                    session,
                    None,
                    f"owner.{args.action}",
                    "terminal",
                    outcome="failure",
                    details={"control": "deployment-terminal", "error": "rejected"},
                )
            raise SystemExit(str(exc)) from None
        print("Owner credentials saved. Sign in as owner_god through the private HTTPS website.")
    finally:
        checks.close()


if __name__ == "__main__":
    main()
