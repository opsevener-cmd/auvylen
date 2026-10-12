from datetime import timedelta
from uuid import uuid4

import pytest
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.credits.models import CreditTransaction, Wallet
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess, ResearchJob
from aevyra_api.research.storage import PrivateArtifactStore
from aevyra_api.research.worker import run_one
from sqlalchemy import func, select
from test_credits import credits as credits
from test_credits import csrf_headers, register, user_id
from test_deployment_config import deployment_settings


def enable(fixture):
    fixture.client.app.state.settings.research_mode = True
    with fixture.sessions.begin() as session:
        session.add(ResearchAccess(user_id=user_id(fixture), enabled=True, reason="test research"))


def submit(fixture, key=None, **extra):
    return fixture.client.post(
        "/api/v1/research/jobs",
        json={"idempotency_key": str(key or uuid4()), "provider": "mock", **extra},
        headers=csrf_headers(fixture.client),
    )


def test_research_authenticated_granted_no_credit_deduction(credits):
    assert credits.client.get("/api/v1/research/status").status_code == 401
    register(credits.client)
    assert submit(credits).status_code == 404
    credits.client.app.state.settings.research_mode = True
    assert submit(credits).status_code == 403
    enable(credits)
    key = uuid4()
    response = submit(credits, key)
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert submit(credits, key).json()["id"] == response.json()["id"]
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    assert run_one(queue)
    assert not run_one(queue)
    job = credits.client.get(f"/api/v1/research/jobs/{response.json()['id']}").json()
    assert job["status"] == "COMPLETED"
    assert job["result"]["synthetic"] is True
    assert job["result"]["engine"] == "mock"
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 0
        assert session.scalar(select(Wallet.cached_balance)) == 0


def test_research_ownership_limits_and_unavailable_models(credits):
    register(credits.client)
    enable(credits)
    for provider in ("custom", "comboloss", "fpem", "faclip", "swingfvqa-ca"):
        assert submit(credits, provider=provider).status_code == 503
    assert submit(credits, user_id=str(uuid4())).status_code == 422
    first = submit(credits).json()
    assert submit(credits).status_code == 202
    assert submit(credits).status_code == 429
    register(credits.client, "another-researcher")
    assert credits.client.get(f"/api/v1/research/jobs/{first['id']}").status_code == 404
    assert credits.client.get("/api/v1/research/jobs").json() == []


def test_expired_lease_reclaims_and_fences_old_worker(credits):
    register(credits.client)
    enable(credits)
    job_id = submit(credits).json()["id"]
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    old = queue.claim()
    assert old
    with credits.sessions.begin() as session:
        job = session.get(ResearchJob, old.id)
        job.lease_until = now() - timedelta(seconds=1)
    new = queue.claim()
    assert new and new.token != old.token
    assert not queue.finish(old, {"synthetic": True})
    assert queue.finish(new, {"synthetic": True})
    assert not queue.finish(new, {"synthetic": True})
    assert credits.client.get(f"/api/v1/research/jobs/{job_id}").json()["status"] == "COMPLETED"


def test_retry_limit_and_revocation(credits):
    register(credits.client)
    enable(credits)
    submit(credits)
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    for _ in range(3):
        lease = queue.claim()
        assert lease
        with credits.sessions.begin() as session:
            session.get(ResearchJob, lease.id).lease_until = now() - timedelta(seconds=1)
    assert queue.claim() is None
    assert credits.client.get("/api/v1/research/jobs").json()[0]["status"] == "FAILED"
    submit(credits)
    lease = queue.claim()
    with credits.sessions.begin() as session:
        session.get(ResearchAccess, user_id(credits)).enabled = False
    assert queue.finish(lease, {"synthetic": True})
    assert all(
        job["status"] == "FAILED" for job in credits.client.get("/api/v1/research/jobs").json()
    )


def test_production_never_executes_mock_research(credits):
    register(credits.client)
    enable(credits)
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    job = queue.enqueue(user_id(credits), "mock", str(uuid4()))
    queue.settings = deployment_settings(research_mode=True)
    with pytest.raises(DomainError):
        queue.enqueue(user_id(credits), "mock", str(uuid4()))
    assert run_one(queue)
    with credits.sessions() as session:
        assert session.get(ResearchJob, job.id).status == "FAILED"
        assert session.get(ResearchJob, job.id).result is None


def test_private_artifacts_ownership_limits_and_persistence(tmp_path):
    store = PrivateArtifactStore(tmp_path, max_bytes=20)
    owner = uuid4()
    artifact, digest = store.put(owner, b"test-artifact")
    assert len(digest) == 64
    assert PrivateArtifactStore(tmp_path, max_bytes=20).read(owner, artifact) == b"test-artifact"
    with pytest.raises(FileNotFoundError):
        store.read(uuid4(), artifact)
    with pytest.raises(ValueError):
        store.put(owner, b"x" * 21)


def test_lease_renewal_and_owner_cancellation_fence_results(credits):
    register(credits.client)
    enable(credits)
    job = submit(credits).json()
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    lease = queue.claim()
    assert queue.renew(lease)
    response = credits.client.post(
        f"/api/v1/research/jobs/{job['id']}/cancel", json={}, headers=csrf_headers(credits.client)
    )
    assert response.status_code == 200
    assert response.json()["failure_reason"] == "Cancelled by owner"
    assert not queue.renew(lease)
    assert not queue.finish(lease, {"synthetic": True})
    assert queue.claim() is None
    assert (
        credits.client.post(f"/api/v1/research/jobs/{job['id']}/cancel", json={}).status_code == 403
    )
    register(credits.client, "other-cancelling-owner")
    assert (
        credits.client.post(
            f"/api/v1/research/jobs/{job['id']}/cancel",
            json={},
            headers=csrf_headers(credits.client),
        ).status_code
        == 404
    )


def test_expired_and_revoked_leases_cannot_renew(credits):
    register(credits.client)
    enable(credits)
    submit(credits)
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    lease = queue.claim()
    with credits.sessions.begin() as session:
        session.get(ResearchJob, lease.id).lease_until = now() - timedelta(seconds=1)
    assert not queue.renew(lease)
    fresh = queue.claim()
    assert fresh and queue.renew(fresh)
    with credits.sessions.begin() as session:
        session.get(ResearchAccess, user_id(credits)).enabled = False
    assert not queue.renew(fresh)
