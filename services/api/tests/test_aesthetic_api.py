"""Phase 6B: authorization, privacy, idempotency and fail-closed behaviour of aesthetic analysis.

The checkpoint here is trained on generated data, flagged synthetic, and accepted only via the
development/test-only setting. It verifies plumbing, never real prediction quality.
"""

import json
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import numpy as np
import pytest
from aevyra_api.aesthetic.models import AestheticAnalysis
from aevyra_api.aesthetic.service import AestheticService
from aevyra_api.config import Settings
from aevyra_api.credits.models import CreditTransaction, User
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess, ResearchJob
from aevyra_api.research.worker import run_one
from aevyra_inference.aesthetic import fit_scoring_head
from aevyra_inference.aesthetic_checkpoint import DatasetEvidence, write_checkpoint
from aevyra_inference.extractors import BASELINE
from PIL import Image
from pydantic import ValidationError
from sqlalchemy import func, select
from test_credits import credits as credits
from test_credits import csrf_headers, register, user_id
from test_research import enable

BASE = "/api/v1/research/aesthetic"
CONSENT = {
    "adult_subject_attested": True,
    "single_subject_attested": True,
    "authorized_consent": True,
}


def generated_checkpoint(root: Path) -> str:
    rng = np.random.default_rng(1)
    direction = rng.normal(0, 1, 230)
    rows, votes, ids = [], [], []
    for subject in range(200):
        base = rng.normal(0, 1, 230)
        for _ in range(3):
            x = base + rng.normal(0, 0.3, 230)
            quality = float(x @ direction) / np.linalg.norm(direction)
            logits = -0.8 * (np.arange(1, 6) - (3 + 1.2 * quality)) ** 2
            p = np.exp(logits - logits.max())
            votes.append(rng.multinomial(25, p / p.sum()))
            rows.append(x)
            ids.append(f"generated-{subject}")
    head, metrics = fit_scoring_head(np.asarray(rows), np.asarray(votes, dtype=float), ids)
    _, sha = write_checkpoint(
        root,
        head,
        model_version="generated-test-v1",
        extractor=BASELINE,
        dataset=DatasetEvidence(
            name="Generated synthetic fixture",
            license="Test-only generated data",
            terms_url="https://example.invalid/test-only",
            authorization_reference="TEST-ONLY",
            reviewer="automated test",
            annotator_population="simulated raters",
            adult_subjects_confirmed=True,
            rating_scale="five ordered categories, 1 (lowest) to 5 (highest)",
            synthetic=True,
        ),
        training={"seed": 42},
        metrics=metrics,
    )
    return sha


@pytest.fixture(scope="module")
def checkpoint_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("aesthetic-models")
    return root, generated_checkpoint(root)


def photo(size=(320, 400), format="PNG"):
    gradient = np.linspace(0, 255, size[0] * size[1] * 3, dtype=np.float64)
    pixels = gradient.reshape(size[1], size[0], 3).astype(np.uint8)
    output = BytesIO()
    Image.fromarray(pixels).save(output, format=format)
    return output.getvalue()


def configure(fixture, checkpoint_root=None):
    register(fixture.client)
    enable(fixture)
    settings = fixture.client.app.state.settings
    settings.private_upload_root = Path.cwd() / "private-uploads"
    if checkpoint_root is not None:
        root, sha = checkpoint_root
        settings.private_model_root = root
        settings.aesthetic_scoring_enabled = True
        settings.aesthetic_model_version = "generated-test-v1"
        settings.aesthetic_manifest_sha256 = sha
        settings.aesthetic_allow_synthetic_test_checkpoint = True
    return settings


def submit(fixture, payload=None, *, key=None, consent=CONSENT, content_type="image/png"):
    metadata = quote(json.dumps({"idempotency_key": str(key or uuid4()), **consent}))
    return fixture.client.post(
        BASE + "/analyses",
        content=photo() if payload is None else payload,
        headers={
            **csrf_headers(fixture.client),
            "Content-Type": content_type,
            "X-Upload-Metadata": metadata,
        },
    )


def execute(fixture):
    assert run_one(ResearchQueue(fixture.sessions, fixture.client.app.state.settings))


def stored_files(settings):
    root = settings.private_upload_root / "aesthetic"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_scoring_is_unavailable_and_fails_closed_without_a_validated_checkpoint(credits):
    assert credits.client.get(BASE + "/status").status_code == 401
    settings = configure(credits)
    status = credits.client.get(BASE + "/status").json()
    assert status["available"] is False and status["reason"] == "disabled"
    assert status["model"] is None and status["limitations"]
    response = submit(credits)
    assert response.status_code == 503
    assert "no validated model" in response.json()["detail"]
    settings.aesthetic_scoring_enabled = True
    settings.aesthetic_model_version = "missing-v1"
    settings.aesthetic_manifest_sha256 = "0" * 64
    assert credits.client.get(BASE + "/status").json()["reason"] == "checkpoint_missing"
    assert submit(credits).status_code == 503
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ResearchJob)) == 0
    assert stored_files(settings) == []


def test_synthetic_checkpoint_is_rejected_by_the_release_gate_by_default(credits, checkpoint_root):
    settings = configure(credits, checkpoint_root)
    settings.aesthetic_allow_synthetic_test_checkpoint = False
    status = credits.client.get(BASE + "/status").json()
    assert (status["available"], status["reason"]) == (False, "validation_gate_failed")
    assert submit(credits).status_code == 503


def test_end_to_end_analysis_deletes_image_and_spends_no_credits(credits, checkpoint_root):
    settings = configure(credits, checkpoint_root)
    status = credits.client.get(BASE + "/status").json()
    assert status["available"] is True and status["model"]["synthetic"] is True
    assert status["model"]["calibration_version"] == "generated-test-v1+split-conformal-90"
    key = uuid4()
    queued = submit(credits, key=key)
    assert queued.status_code == 202, queued.text
    body = queued.json()
    assert body["status"] == "QUEUED" and body["result"] is None and body["image_retained"]
    assert submit(credits, key=key).json()["id"] == body["id"]  # Idempotent retry.
    assert len(stored_files(settings)) == 1
    execute(credits)
    done = credits.client.get(f"{BASE}/analyses/{body['id']}").json()
    assert done["status"] == "COMPLETED", done
    result = done["result"]
    assert 1 <= result["score_10"] <= 10
    assert result["display_score"] == pytest.approx(result["score_10"])
    assert result["score_10"] == pytest.approx(1 + 2.25 * (result["expected_rating_5"] - 1))
    assert sum(result["rating_distribution"]) == pytest.approx(1)
    assert result["synthetic"] is True and result["engine"] == "auvylen-aesthetic"
    assert result["version"] == done["model_version"] == "generated-test-v1"
    assert result["interval_low"] <= result["score_10"] <= result["interval_high"]
    assert result["adult_basis"] == "user_attestation"
    assert result["automated_face_detection"] == "not_implemented"
    assert done["image_retained"] is False and stored_files(settings) == []
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 0
    assert [a["id"] for a in credits.client.get(BASE + "/analyses").json()] == [body["id"]]


def test_consent_format_size_and_csrf_are_enforced_before_storage(credits, checkpoint_root):
    settings = configure(credits, checkpoint_root)
    missing = {k: v for k, v in CONSENT.items() if k != "single_subject_attested"}
    assert submit(credits, consent=missing).status_code == 422
    assert submit(credits, consent={**CONSENT, "adult_subject_attested": False}).status_code == 422
    assert submit(credits, content_type="application/json").status_code == 415
    assert submit(credits, photo((160, 160))).status_code == 422
    assert submit(credits, photo((900, 240))).status_code == 422
    blank = BytesIO()
    Image.new("RGB", (300, 300), (120, 120, 120)).save(blank, "PNG")
    assert "blank" in submit(credits, blank.getvalue()).json()["detail"]
    assert submit(credits, b"not an image").status_code == 422
    no_csrf = credits.client.post(
        BASE + "/analyses",
        content=photo(),
        headers={"Content-Type": "image/png", "X-Upload-Metadata": quote(json.dumps(CONSENT))},
    )
    assert no_csrf.status_code == 403
    assert stored_files(settings) == []


def test_analyses_are_private_to_their_owner_and_deletable(credits, checkpoint_root):
    settings = configure(credits, checkpoint_root)
    first = submit(credits).json()
    execute(credits)
    owner = user_id(credits)
    credits.client.post("/api/v1/auth/logout", json={}, headers=csrf_headers(credits.client))
    register(credits.client, "second@example.test")
    with credits.sessions.begin() as session:
        other = session.scalar(select(User.id).where(User.id != owner))
        session.add(ResearchAccess(user_id=other, enabled=True, reason="second test user"))
    assert credits.client.get(f"{BASE}/analyses/{first['id']}").status_code == 404
    assert credits.client.get(BASE + "/analyses").json() == []
    deleted = credits.client.post(
        f"{BASE}/analyses/{first['id']}/delete", json={}, headers=csrf_headers(credits.client)
    )
    assert deleted.status_code == 404
    second = submit(credits).json()
    deleted = credits.client.post(
        f"{BASE}/analyses/{second['id']}/delete", json={}, headers=csrf_headers(credits.client)
    )
    assert deleted.status_code == 200
    assert credits.client.get(f"{BASE}/analyses/{second['id']}").status_code == 404
    with credits.sessions() as session:
        assert session.get(AestheticAnalysis, UUID(second["id"])) is None
        job = session.scalar(select(ResearchJob).where(ResearchJob.user_id == other))
        assert job.status == "FAILED" and job.result is None
    assert stored_files(settings) == []
    assert run_one(ResearchQueue(credits.sessions, settings)) is False  # Nothing left to run.


def test_tampered_checkpoint_after_submission_fails_without_a_result(credits, tmp_path):
    root = tmp_path / "tamper-models"
    sha = generated_checkpoint(root)
    settings = configure(credits, (root, sha))
    queued = submit(credits).json()
    head = root / "aesthetic" / "generated-test-v1" / "head.f64"
    head.parent.chmod(0o700)
    head.chmod(0o600)
    data = head.read_bytes()
    head.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    execute(credits)
    view = credits.client.get(f"{BASE}/analyses/{queued['id']}").json()
    assert view["status"] == "FAILED" and view["result"] is None
    assert view["image_retained"] is False and stored_files(settings) == []
    assert credits.client.get(BASE + "/status").json()["reason"] == "checkpoint_integrity_failure"


def test_revoked_research_access_blocks_submission_and_execution(credits, checkpoint_root):
    configure(credits, checkpoint_root)
    queued = submit(credits).json()
    with credits.sessions.begin() as session:
        session.get(ResearchAccess, user_id(credits)).enabled = False
    assert submit(credits).status_code == 403
    assert credits.client.get(BASE + "/analyses").status_code == 403
    # The queue refuses to lease work for a revoked user and fails the job instead.
    assert run_one(ResearchQueue(credits.sessions, credits.client.app.state.settings)) is False
    with credits.sessions() as session:
        row = session.get(AestheticAnalysis, UUID(queued["id"]))
        job = session.get(ResearchJob, row.job_id)
        assert job.status == "FAILED" and job.result is None
    AestheticService(credits.sessions, credits.client.app.state.settings).purge()
    with credits.sessions() as session:
        assert session.get(AestheticAnalysis, UUID(queued["id"])).artifact_id is None


def test_settings_require_a_pinned_checkpoint_and_forbid_synthetic_deployments():
    with pytest.raises(ValidationError):
        Settings(api_environment="test", aesthetic_scoring_enabled=True, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(
            api_environment="test",
            aesthetic_scoring_enabled=True,
            aesthetic_model_version="../x",
            aesthetic_manifest_sha256="0" * 64,
            _env_file=None,
        )
    for environment in ("staging", "production"):
        with pytest.raises(ValidationError, match="forbidden in deployments"):
            Settings(
                api_environment=environment,
                aesthetic_allow_synthetic_test_checkpoint=True,
                _env_file=None,
            )
    assert Settings(api_environment="test", _env_file=None).aesthetic_scoring_enabled is False
    blank = Settings(
        api_environment="test",
        aesthetic_model_version="",
        aesthetic_manifest_sha256="",
        _env_file=None,
    )
    assert blank.aesthetic_model_version is None and blank.aesthetic_manifest_sha256 is None
