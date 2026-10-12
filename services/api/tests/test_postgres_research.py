from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from aevyra_api.accounts import AccountService
from aevyra_api.config import Settings
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess, ResearchJob
from sqlalchemy import func, select
from test_postgres_commercial import postgres_services

pytestmark = pytest.mark.integration


def test_concurrent_enqueue_and_claim_are_durable():
    with postgres_services() as (sessions, *_):
        settings = Settings(api_environment="test", research_mode=True, _env_file=None)
        user, _ = AccountService(sessions, settings).register(
            "research-worker", "test-research-password"
        )
        with sessions.begin() as session:
            session.add(ResearchAccess(user_id=user.id, enabled=True, reason="test"))
        queue = ResearchQueue(sessions, settings)
        key = str(uuid4())
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(lambda _: queue.enqueue(user.id, "mock", key).id, range(6)))
        assert len(set(ids)) == 1
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(ResearchJob)) == 1
        with ThreadPoolExecutor(max_workers=6) as pool:
            leases = list(pool.map(lambda _: queue.claim(), range(6)))
        assert sum(lease is not None for lease in leases) == 1
        lease = next(lease for lease in leases if lease)
        # A new queue instance sees persisted work and cannot claim the active lease.
        recovered = ResearchQueue(sessions, settings)
        assert recovered.claim() is None
        assert recovered.finish(lease, {"synthetic": True})
