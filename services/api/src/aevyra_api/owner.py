"""Interactive private-Codespaces-only Owner initialization; never store plaintext secrets."""

import getpass
import os
import secrets
import sys
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.accounts import HASHER, OWNER_LOGIN
from aevyra_api.config import Settings
from aevyra_api.credits.models import User, Wallet
from aevyra_api.database import DependencyChecks
from aevyra_api.research.models import ResearchAccess


def provision(sessions: sessionmaker[Session], password: str) -> str:
    """Create exactly one Owner; do not hijack an existing ordinary username."""
    if not 12 <= len(password) <= 128:
        raise ValueError("Owner password length must be 12–128 characters")
    with sessions.begin() as session:
        if session.scalar(select(User).where(User.role == "owner").with_for_update()):
            raise RuntimeError("Owner account already exists; password unchanged")
        if session.scalar(select(User).where(User.login_identifier == OWNER_LOGIN)):
            raise RuntimeError("Reserved Owner login is already occupied; manual review required")
        user = User(public_user_id="usr_" + uuid4().hex, login_identifier=OWNER_LOGIN,
                    password_hash=HASHER.hash(password), role="owner")
        session.add(user)
        session.flush()
        session.add(Wallet(user_id=user.id))
        session.add(ResearchAccess(user_id=user.id, enabled=True,
            reason="Private Codespaces Owner bootstrap"))
    return OWNER_LOGIN


def main() -> None:
    if (os.environ.get("CODESPACES") != "true"
            or not os.environ.get("CODESPACE_NAME")
            or os.environ.get("APP_ENV") != "staging"
            or not sys.stdin.isatty()):
        raise SystemExit("Run interactive Owner initialization only in your private Codespace")
    first = getpass.getpass("New Owner password (not the one shared in chat): ")
    second = getpass.getpass("Confirm new Owner password: ")
    if not secrets.compare_digest(first, second):
        raise SystemExit("Passwords do not match")
    checks = DependencyChecks(Settings())
    try:
        try:
            name = provision(checks.sessions, first)
        except (RuntimeError, ValueError) as exc:
            raise SystemExit(str(exc)) from None
        print(f"Owner account created: {name}; sign in via the existing HTTPS login page")
    finally:
        checks.close()


if __name__ == "__main__":
    main()
