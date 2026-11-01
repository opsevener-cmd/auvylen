"""Isolated SQLite tests. Stubbed child output is a contract fixture, never model evidence."""

import hashlib
import json
import os
import time
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from aevyra_api.commercial.models import now
from aevyra_api.config import Settings
from aevyra_api.credits.models import AccountSession
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchJob
from aevyra_api.research.native_preview import NativePreview, canonical
from aevyra_api.research.worker import run_one
from aevyra_inference.native_checkpoint import load
from PIL import Image
from sqlalchemy import select
from test_credits import credits as credits
from test_credits import csrf_headers, register
from test_owner import owner

BASE = "/api/v1/research/native-preview"
PIN = "a" * 64


def image(size=(224, 224)):
    output = BytesIO()
    Image.new("RGB", size, (90, 100, 120)).save(output, "PNG")
    return output.getvalue()


def setup(credits, tmp_path):
    owner(credits)
    settings = Settings(
        api_environment="test",
        research_mode=True,
        native_preview_enabled=True,
        native_preview_checkpoint=tmp_path / "checkpoint",
        native_preview_manifest_sha256=PIN,
        native_preview_review_reference="unit-test-contract-fixture-not-model-evidence",
        private_upload_root=tmp_path / "uploads",
        _env_file=None,
    )
    credits.client.app.state.settings = settings
    return NativePreview(credits.sessions, settings)


def submit(credits, payload=None, key=None, **overrides):
    metadata = dict(
        idempotency_key=str(key or uuid4()),
        adult_subject_attested=True,
        single_subject_attested=True,
        authorized_consent=True,
    )
    metadata.update(overrides)
    return credits.client.post(
        BASE + "/jobs",
        content=payload or image(),
        headers={
            **csrf_headers(credits.client),
            "Content-Type": "image/png",
            "X-Upload-Metadata": quote(json.dumps(metadata)),
        },
    )


def fixture_result():
    return dict(
        predicted_rating=4.25,
        native_scale=[1, 7],
        manifest_sha256=PIN,
        encoder="contract-fixture",
        collection="contract-fixture",
        research_only=True,
        synthetic=False,
        consumer_enabled=False,
        release_failures=["insufficient_test_subjects"],
        duration_ms=1.0,
        peak_rss_kib=1000,
    )


def test_disabled_ordinary_access_csrf_and_production(credits, tmp_path):
    assert credits.client.get(BASE + "/status").status_code == 401
    register(credits.client, "ordinary-preview")
    assert credits.client.get(BASE + "/status").status_code == 403
    owner(credits)
    assert credits.client.get(BASE + "/status").json()["available"] is False
    assert submit(credits).status_code == 503
    assert credits.client.post(BASE + "/jobs", content=image()).status_code == 403
    for environment in ("staging", "production"):
        with pytest.raises(ValueError, match="private development/test"):
            Settings(
                api_environment=environment,
                research_mode=True,
                native_preview_enabled=True,
                native_preview_checkpoint=tmp_path,
                native_preview_manifest_sha256=PIN,
                native_preview_review_reference="fixture",
                _env_file=None,
            )


def test_upload_idempotency_fresh_auth_and_deletion_fencing(credits, tmp_path):
    service = setup(credits, tmp_path)
    with patch.object(NativePreview, "ready", return_value=None):
        assert submit(credits, adult_subject_attested=False).status_code == 422
        assert submit(credits, payload=b"not-an-image").status_code == 422
        assert submit(credits, payload=b"x" * (4 * 1024**2 + 1)).status_code == 413
        key = uuid4()
        response = submit(credits, key=key)
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        assert submit(credits, key=key).json()["id"] == job_id
        assert len(list(service.store.root.rglob("*/*"))) == 1
        assert credits.client.get("/api/v1/research/jobs").json() == []
        assert credits.client.get("/api/v1/research/jobs/" + job_id).status_code == 404
        assert (
            credits.client.post(
                "/api/v1/research/jobs/" + job_id + "/cancel",
                json={},
                headers=csrf_headers(credits.client),
            ).status_code
            == 404
        )
        lease = service.queue.claim()
        assert lease is not None
        assert (
            credits.client.post(
                BASE + "/jobs/" + job_id + "/delete", json={}, headers=csrf_headers(credits.client)
            ).status_code
            == 200
        )
        assert service.queue.finish(lease, fixture_result()) is False
        assert credits.client.get(BASE + "/jobs/" + job_id).status_code == 404
        assert len(list(service.store.root.rglob("*/*"))) == 0
        with credits.sessions.begin() as session:
            auth = session.scalar(select(AccountSession))
            auth.created_at = now() - timedelta(minutes=20)
        assert submit(credits).status_code == 403


def test_worker_contract_and_retention(credits, tmp_path):
    service = setup(credits, tmp_path)
    with patch.object(NativePreview, "ready", return_value=None):
        response = submit(credits)
        job_id = response.json()["id"]
        with patch(
            "aevyra_api.research.native_preview.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=json.dumps(fixture_result())),
        ):
            assert run_one(service.queue)
        record = credits.client.get(BASE + "/jobs/" + job_id).json()
        assert record["status"] == "COMPLETED"
        assert record["result"]["native_scale"] == [1, 7]
        assert "artifact" not in record["payload"]
        assert not list(service.store.root.rglob("*/*"))
        with credits.sessions.begin() as session:
            job = session.get(ResearchJob, UUID(job_id))
            job.created_at = now() - timedelta(hours=25)
        assert credits.client.get(BASE + "/jobs/" + job_id).status_code == 404
        with credits.sessions() as session:
            assert session.get(ResearchJob, UUID(job_id)).result is None


def test_failure_no_fallback_and_queued_expiry(credits, tmp_path):
    service = setup(credits, tmp_path)
    with patch.object(NativePreview, "ready", return_value=None):
        job_id = submit(credits).json()["id"]
        with patch("aevyra_api.research.native_preview.subprocess.run", side_effect=TimeoutError):
            assert run_one(service.queue)
        record = credits.client.get(BASE + "/jobs/" + job_id).json()
        assert record["status"] == "FAILED" and record["result"] is None
        job_id = submit(credits).json()["id"]
        with credits.sessions.begin() as session:
            job = session.get(ResearchJob, UUID(job_id))
            job.created_at = now() - timedelta(hours=2)
        service.purge()
        assert service.queue.claim() is None
        assert not list(service.store.root.rglob("*/*"))


@pytest.mark.parametrize("size", [(224, 224), (224, 4096)])
def test_lossless_preparation_strips_metadata(size):
    payload = image(size)
    with Image.open(BytesIO(payload)) as original, Image.open(BytesIO(canonical(payload))) as clean:
        assert original.convert("RGB").tobytes() == clean.tobytes()
        assert not clean.getexif()


@pytest.mark.pretrained
def test_real_native_preview_cpu_end_to_end(credits, tmp_path, monkeypatch):
    """Opt-in private assets. Real portrait, existing checkpoint, no fitting/test-set tuning."""
    root = os.environ.get("AUVYLEN_PREVIEW_VERIFY_ROOT")
    photo = os.environ.get("AUVYLEN_PREVIEW_VERIFY_IMAGE")
    if not root or not photo:
        pytest.skip(
            "Requires reviewed private human checkpoint and authorized development portrait"
        )
    root = Path(root)
    pin = hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()
    owner(credits)
    settings = Settings(
        api_environment="test",
        research_mode=True,
        native_preview_enabled=True,
        native_preview_checkpoint=root,
        native_preview_manifest_sha256=pin,
        native_preview_review_reference="London-author-release-closed-research-20261101",
        private_model_root=Path(os.environ["AUVYLEN_PREVIEW_VERIFY_ENCODER_ROOT"]).parent,
        private_upload_root=tmp_path / "uploads",
        _env_file=None,
    )
    credits.client.app.state.settings = settings
    status = credits.client.get(BASE + "/status")
    assert status.json()["available"] is True, status.text
    assert status.json()["consumer_enabled"] is False
    with pytest.raises(ValueError, match="release review"):
        load(root, pin)
    from aevyra_inference.native_checkpoint import NativeProvider

    monkeypatch.setenv("AUVYLEN_NATIVE_MANIFEST_SHA256", pin)
    assert NativeProvider().availability(root).reason == "validation_gate_failed"
    payload = Path(photo).read_bytes()
    upload_started = time.perf_counter()
    response = submit(credits, payload=payload)
    upload_ms = (time.perf_counter() - upload_started) * 1000
    assert response.status_code == 202, response.text
    started = time.perf_counter()
    assert run_one(ResearchQueue(credits.sessions, settings))
    record = credits.client.get(BASE + "/jobs/" + response.json()["id"]).json()
    worker_and_read_ms = (time.perf_counter() - started) * 1000
    upload_to_verified_read_ms = (time.perf_counter() - upload_started) * 1000
    assert record["status"] == "COMPLETED", record
    result = record["result"]
    assert result["research_only"] and result["native_scale"] == [1, 7]
    from aevyra_inference.native_preview import predict

    direct = predict(root, pin, settings.private_model_root / "pretrained", payload)
    assert abs(result["predicted_rating"] - direct["predicted_rating"]) < 1e-8
    assert not list((tmp_path / "uploads").rglob("*/*/*"))
    evidence = {
        k: result[k] for k in ("manifest_sha256", "duration_ms", "peak_rss_kib", "native_scale")
    }
    evidence.update(
        worker_and_read_ms=worker_and_read_ms,
        upload_acceptance_ms=upload_ms,
        upload_to_verified_read_ms=upload_to_verified_read_ms,
        saved_pixel_prediction_difference=abs(
            result["predicted_rating"] - direct["predicted_rating"]
        ),
        genuine_inference=True,
        consumer_enabled=False,
    )
    output = os.environ.get("AUVYLEN_PREVIEW_VERIFY_EVIDENCE")
    if output:
        Path(output).write_text(json.dumps(evidence, indent=2) + "\n")
    assert (
        credits.client.post(
            BASE + "/jobs/" + response.json()["id"] + "/delete",
            json={},
            headers=csrf_headers(credits.client),
        ).status_code
        == 200
    )


def test_invalid_checkpoint_orphan_cleanup_and_account_separation(credits, tmp_path):
    service = setup(credits, tmp_path)
    status = credits.client.get(BASE + "/status")
    assert status.status_code == 200 and status.json()["available"] is False
    assert submit(credits).status_code == 503
    with patch.object(NativePreview, "ready", return_value=None):
        job_id = submit(credits).json()["id"]
        with credits.sessions() as session:
            job = session.get(ResearchJob, UUID(job_id))
            orphan, _ = service.store.put(job.user_id, image())
            path = service.store._path(job.user_id, orphan)
        os.utime(path, (time.time() - 3700, time.time() - 3700))
        service.purge()
        assert not path.exists()
        register(credits.client, "other-preview-account")
        assert credits.client.get(BASE + "/jobs/" + job_id).status_code == 403
        assert (
            credits.client.post(
                BASE + "/jobs/" + job_id + "/delete", json={}, headers=csrf_headers(credits.client)
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "bad", [dict(predicted_rating=9), dict(consumer_enabled=True), dict(synthetic=True)]
)
def test_worker_rejects_invalid_or_consumer_result(credits, tmp_path, bad):
    service = setup(credits, tmp_path)
    with patch.object(NativePreview, "ready", return_value=None):
        job_id = submit(credits).json()["id"]
        with patch(
            "aevyra_api.research.native_preview.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps({**fixture_result(), **bad})
            ),
        ):
            assert run_one(service.queue)
        record = credits.client.get(BASE + "/jobs/" + job_id).json()
        assert record["status"] == "FAILED" and record["result"] is None
        assert not list(service.store.root.rglob("*/*"))


def test_review_change_before_completion_cannot_publish(credits, tmp_path):
    service = setup(credits, tmp_path)
    with patch.object(NativePreview, "ready", return_value=None):
        job_id = submit(credits).json()["id"]

        def change_review(*args, **kwargs):
            service.settings.native_preview_review_reference = "changed-during-execution"
            return SimpleNamespace(returncode=0, stdout=json.dumps(fixture_result()))

        with patch("aevyra_api.research.native_preview.subprocess.run", side_effect=change_review):
            assert run_one(service.queue)
        record = credits.client.get(BASE + "/jobs/" + job_id).json()
        assert record["status"] == "FAILED" and record["result"] is None


def test_poll_expires_only_requested_job_and_status_does_not_lock(credits, tmp_path):
    service = setup(credits, tmp_path)
    with patch.object(NativePreview, "ready", return_value=None):
        polled, other = submit(credits).json()["id"], submit(credits).json()["id"]
        with credits.sessions.begin() as session:
            for job_id in (polled, other):
                session.get(ResearchJob, UUID(job_id)).created_at = now() - timedelta(hours=2)
        with patch.object(NativePreview, "purge", side_effect=AssertionError("global sweep")):
            assert credits.client.get(BASE + "/jobs/" + polled).status_code == 404
        with credits.sessions() as session:
            assert session.get(ResearchJob, UUID(polled)).payload == {
                "operation": "native_research_preview",
                "deleted": True,
            }
            # The unpolled job waits for the worker's periodic sweep.
            assert session.get(ResearchJob, UUID(other)).status == "QUEUED"
        assert len(list(service.store.root.rglob("*/*"))) == 1
        service.purge()
        assert not list(service.store.root.rglob("*/*"))
    with patch.object(NativePreview, "access", autospec=True) as access:
        credits.client.get(BASE + "/status")
    assert access.call_args.kwargs == {"lock": False}
