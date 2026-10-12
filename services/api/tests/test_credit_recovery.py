from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from aevyra_api.commercial.models import Analysis
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.models import CreditTransaction, Wallet
from aevyra_inference.engine import EngineRegistry
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from test_credits import credits, grant, make_batch, register, user_id

# Imported fixture is deliberately exposed to pytest in this module.
assert credits


def test_crash_after_deduction_recovers_without_double_spend(credits):
    register(credits.client)
    grant(credits)
    service = CreditAnalysisService(
        credits.sessions, EngineRegistry([credits.engine]), production=False
    )
    key = str(uuid4())
    with patch.object(service, "fulfill", side_effect=RuntimeError("process interrupted")):
        with pytest.raises(RuntimeError):
            service.create(user_id(credits), "aevyra-test-analysis", key)
    with credits.sessions() as session:
        assert session.scalar(select(Analysis.status)) == "CREATED"
        assert session.scalar(select(Wallet.cached_balance)) == 9
    analysis_id = service.create(user_id(credits), "aevyra-test-analysis", key)
    assert service.create(user_id(credits), "aevyra-test-analysis", key) == analysis_id
    assert credits.engine.calls == 1
    with credits.sessions() as session:
        assert session.scalar(select(Wallet.cached_balance)) == 9
        assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 2


def test_downgrade_refuses_unredeemed_batch_even_without_accounts(credits):
    make_batch(credits)
    path = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(path))
    with credits.sessions() as session:
        bind = session.get_bind()
        with bind.begin() as connection:
            config.attributes["connection"] = connection
            with pytest.raises(RuntimeError, match="issued batches"):
                command.downgrade(config, "0002_commercial")
