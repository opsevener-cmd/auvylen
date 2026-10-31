"""Security/transport fixtures only: these tests do not validate aesthetic predictions."""

import hashlib
import importlib.util
import json
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchJob
from aevyra_api.routes.pretrained import canonical, purge_pretrained, store
from aevyra_inference.providers import ProviderStatus
from PIL import Image
from sqlalchemy import select
from test_credits import credits as credits
from test_credits import csrf_headers, register, user_id
from test_research import enable


def adapter():
    path = (
        Path(__file__).resolve().parents[3] / "plugins/comboloss/src/auvylen_comboloss/__init__.py"
    )
    spec = importlib.util.spec_from_file_location("comboloss_test_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image():
    b = BytesIO()
    Image.new("RGB", (240, 300), (23, 71, 113)).save(b, format="PNG")
    return b.getvalue()


def test_checkpoint_rights_and_hash_gate(tmp_path, monkeypatch):
    module = adapter()
    assert not module.Provider().availability(tmp_path).available
    data = {
        "source_commit": module.SOURCE,
        "native_scale": [1, 5],
        "reference_verified": True,
        "checkpoint_sha256": hashlib.sha256(b"test-only-not-a-model").hexdigest(),
    }
    (tmp_path / "checkpoint.pth").write_bytes(b"test-only-not-a-model")

    def write():
        raw = json.dumps(data).encode()
        (tmp_path / "manifest.json").write_bytes(raw)
        monkeypatch.setenv("COMBOLOSS_MANIFEST_SHA256", hashlib.sha256(raw).hexdigest())

    write()
    assert module.Provider().availability(tmp_path).reason == "unreviewed_license"
    data["rights"] = {
        "reviewer": "TEST ONLY",
        "code_license": "MIT",
        "weights_permission": "TEST ONLY",
        "dataset_permission": "TEST ONLY",
        "research_service_allowed": True,
    }
    write()
    assert module.verified(tmp_path)["native_scale"] == [1, 5]
    (tmp_path / "checkpoint.pth").write_bytes(b"changed")
    with pytest.raises(ValueError):
        module.verified(tmp_path)
    assert module.ComboLoss.normalize(None, 3.125) == 3.125


def test_transport_preserves_pixels():
    raw = image()
    with Image.open(BytesIO(raw)) as original, Image.open(BytesIO(canonical(raw))) as saved:
        assert original.tobytes() == saved.tobytes()
        assert not saved.info


def post(credits):
    return credits.client.post(
        "/api/v1/research/pretrained/comboloss",
        content=image(),
        headers={
            **csrf_headers(credits.client),
            "Content-Type": "image/png",
            "X-Upload-Metadata": json.dumps(
                {
                    "idempotency_key": str(uuid4()),
                    "adult_subject_attested": True,
                    "single_subject_attested": True,
                    "authorized_consent": True,
                }
            ),
        },
    )


def test_access_unavailable_and_private_cleanup(credits, tmp_path, monkeypatch):
    assert credits.client.get("/api/v1/research/status").status_code == 401
    register(credits.client)
    assert post(credits).status_code == 403
    enable(credits)
    settings = credits.client.app.state.settings
    settings.private_upload_root = tmp_path
    assert post(credits).status_code == 503

    class Catalog:
        def status(self, slug):
            return ProviderStatus(slug, "TEST ONLY", True, "ready")

    monkeypatch.setattr("aevyra_api.routes.pretrained.catalog", lambda _: Catalog())
    response = post(credits)
    assert response.status_code == 202
    job_id = response.json()["id"]
    with credits.sessions() as session:
        job = session.get(ResearchJob, UUID(job_id))
        artifact = UUID(job.payload["artifact"])
        assert store(settings).read(user_id(credits), artifact)
    # A worker failure must remove the photograph and publish no score.
    from aevyra_api.research.worker import run_one

    def fail(*args):
        raise RuntimeError("test-only unavailable runtime")

    monkeypatch.setattr("aevyra_api.research.worker.execute_pretrained", fail)
    assert run_one(ResearchQueue(credits.sessions, settings))
    with pytest.raises(FileNotFoundError):
        store(settings).read(user_id(credits), artifact)
    # CSRF remains enforced on removal.
    assert (
        credits.client.post(
            f"/api/v1/research/pretrained/jobs/{job_id}/delete", json={}
        ).status_code
        == 403
    )
    assert (
        credits.client.post(
            f"/api/v1/research/pretrained/jobs/{job_id}/delete",
            json={},
            headers=csrf_headers(credits.client),
        ).status_code
        == 200
    )
    with pytest.raises(FileNotFoundError):
        store(settings).read(user_id(credits), artifact)
    with credits.sessions() as session:
        job = session.scalar(select(ResearchJob).where(ResearchJob.provider == "comboloss"))
        assert job.result is None and job.lease_token is None
    purge_pretrained(ResearchQueue(credits.sessions, settings))
