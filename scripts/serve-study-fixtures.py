"""Disposable Phase 7A browser test server. NEVER a real deployment entry point."""

import os
import tempfile
import threading
import time
from pathlib import Path

if (
    os.environ.get("AUVYLEN_TEST_FIXTURES") != "ISOLATED_SQLITE_ONLY"
    or os.environ.get("APP_ENV") != "test"
):
    raise SystemExit("Explicit isolated test-fixture settings required")

import uvicorn
from aevyra_api.accounts import AccountService
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.main import create_app
from aevyra_api.owner import provision
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
# Public, synthetic test-account credentials. They are never used with a retained database.
FIXTURE_PASSWORD = "synthetic-study-fixture-password-only"


class FixtureLimiter:
    def __init__(self):
        self.items: dict[str, tuple[int, float]] = {}
        self.lock = threading.Lock()

    def check(self, key: str, limit: int, seconds: int) -> None:
        with self.lock:
            count, until = self.items.get(key, (0, 0.0))
            if until <= time.monotonic():
                count, until = 0, time.monotonic() + seconds
            count += 1
            self.items[key] = count, until
            if count > limit:
                raise DomainError("Too many attempts", 429)


with tempfile.TemporaryDirectory(prefix="auvylen-study-fixtures-") as temporary:
    # A fresh in-memory engine, supplied directly to Alembic. No DATABASE_URL is used.
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    migration = Config(str(ROOT / "services/api/alembic.ini"))
    with engine.begin() as connection:
        migration.attributes["connection"] = connection
        command.upgrade(migration, "head")
        command.check(migration)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0
    settings = Settings(
        api_environment="test",
        log_level="WARNING",
        research_mode=True,
        study_collection_enabled=True,
        study_real_collection_enabled=False,
        shared_proxy_rate_limits=True,
        cors_origins=[os.environ.get("STUDY_FIXTURE_ORIGIN", "http://127.0.0.1:3148")],
        private_upload_root=Path(temporary) / "uploads",
        private_model_root=Path(temporary) / "models",
        redemption_code_pepper=SecretStr("synthetic-study-fixture-pepper-not-for-deployment"),
        _env_file=None,
    )
    provision(sessions, FIXTURE_PASSWORD)
    accounts = AccountService(sessions, settings)
    for name in (
        "study-fixture-contributor",
        "study-fixture-rater-0",
        "study-fixture-rater-1",
        "study-fixture-rater-2",
        "study-fixture-custodian",
    ):
        accounts.register(name, FIXTURE_PASSWORD)
    application = create_app(settings)
    application.state.settings = settings
    application.state.sessions = sessions
    application.state.rate_limiter = FixtureLimiter()
    try:
        uvicorn.run(
            application,
            host="127.0.0.1",
            port=int(os.environ.get("STUDY_FIXTURE_PORT", "8148")),
            lifespan="off",
            access_log=False,
            log_level="warning",
        )
    finally:
        engine.dispose()
