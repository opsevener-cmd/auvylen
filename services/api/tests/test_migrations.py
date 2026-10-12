from pathlib import Path

import pytest
from aevyra_api.config import Settings
from aevyra_api.database import build_engine
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect


@pytest.mark.integration
def test_migration_and_schema_match() -> None:
    # Upgrade/check only; never downgrade or destroy a developer's database here.
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    command.upgrade(config, "head")
    command.check(config)
    engine = build_engine(Settings())
    try:
        assert "foundation_records" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
