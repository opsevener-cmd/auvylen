"""Explicitly authorized, serialized deployment migrations; fail without serving."""

import logging
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from aevyra_api.config import Settings
from aevyra_api.database import build_engine
from aevyra_api.logging import configure_logging


def main() -> None:
    if os.environ.get("APPLY_MIGRATIONS") != "true":
        raise SystemExit("Set APPLY_MIGRATIONS=true only after backup/review")
    settings = Settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET statement_timeout = 60000"))
            connection.execute(text("SELECT pg_advisory_lock(418412)"))
            connection.commit()
            try:
                connection.execute(text("SET statement_timeout = 0"))
                connection.commit()
                config = Config("services/api/alembic.ini")
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                command.check(config)
            finally:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(418412)"))
                connection.commit()
    except Exception as exc:
        logging.getLogger("aevyra.migrations").error(
            "deployment_migration_failed", extra={"error_type": type(exc).__name__}
        )
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
