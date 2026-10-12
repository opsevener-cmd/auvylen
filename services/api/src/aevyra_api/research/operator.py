"""Explicit local operator authorization; no public admin route."""

import argparse

from sqlalchemy import select

from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.database import DependencyChecks
from aevyra_api.research.models import ResearchAccess


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant/revoke non-commercial research access")
    parser.add_argument("action", choices=["grant", "revoke"])
    parser.add_argument("public_user_id")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if not 1 <= len(args.reason) <= 200:
        parser.error("Reason must contain 1-200 characters")
    checks = DependencyChecks(Settings())
    try:
        with checks.sessions.begin() as session:
            user = session.scalar(
                select(User).where(User.public_user_id == args.public_user_id).with_for_update()
            )
            if user is None:
                raise SystemExit("User not found")
            access = session.get(ResearchAccess, user.id)
            if access is None:
                access = ResearchAccess(user_id=user.id)
                session.add(access)
            access.enabled = args.action == "grant"
            access.reason = args.reason
        print("Research authorization updated; no Credits changed")
    finally:
        checks.close()


if __name__ == "__main__":
    main()
