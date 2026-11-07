"""Authorized generated fixtures only. No real participants or customer photos."""

import csv
import json
from datetime import timedelta
from io import BytesIO
from urllib.parse import quote
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from aevyra_api.commercial.models import now
from aevyra_api.studies.models import (
    Assignment,
    Photo,
    Study,
)
from aevyra_api.studies.service import Studies
from aevyra_inference.native_data import Collection, load_rows
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from test_credits import PASSWORD, csrf_headers, register
from test_credits import credits as credits
from test_owner import login_owner, owner

BASE = "/api/v1/research/studies"
TEXT_EN = (
    "Authorized fixture study. Adults volunteer portraits and independent subjective 1–7 ratings. "
    "Research cloud processing, training and private derived weights only; "
    "no consumer or commercial scoring. "
    "Withdrawal removes images and ratings, revokes exports; "
    "already downloaded copies cannot be recalled. "
    "Minimal consent, partition and audit evidence remains; no marketing, no identity inference."
)
TEXT_ZH = (
    "这是已获授权的测试研究。仅限成人自愿提供肖像并独立进行主观的1–7分评价。"
    "仅用于私密云端研究处理、训练及研究模型，不用于消费者或商业评分。"
    "可随时撤回并删除照片、评分，撤销导出；已经下载的副本无法远程收回。"
    "保留最少的同意、分区和审计记录，不营销，不推断身份。"
)


def post(credits, path, body):
    return credits.client.post(BASE + path, json=body, headers=csrf_headers(credits.client))


def key():
    return {"idempotency_key": str(uuid4())}


def setup(credits, tmp_path):
    s = credits.client.app.state.settings
    s.study_collection_enabled, s.research_mode = True, True
    s.private_upload_root = tmp_path / "private"
    s.shared_proxy_rate_limits = True
    owner(credits)
    return Studies(credits.sessions, s)


def create(credits, *, partition="development", custodian=None):
    response = post(
        credits,
        "",
        {
            **key(),
            "title": "Authorized fixture study",
            "partition": partition,
            "custodian_public_id": custodian,
        },
    )
    assert response.status_code == 201, response.text
    study = response.json()["id"]
    response = post(
        credits,
        f"/{study}/consent",
        {
            **key(),
            "text_en": TEXT_EN,
            "text_zh": TEXT_ZH,
            "contact_en": "Fixture operator only",
            "contact_zh": "测试负责人",
            "rights_reference": "fixture-rights-v1",
        },
    )
    assert response.status_code == 200, response.text
    code = act(credits, study, "rotate_invite").json()["value"]
    if partition == "development":
        assert act(credits, study, "open").status_code == 200
    return study, code


def act(credits, study, action):
    return post(
        credits,
        f"/{study}/action",
        {**key(), "action": action, "reason": "Authorized fixture workflow"},
    )


def join(credits, code, role, name):
    account = register(credits.client, name)
    response = post(credits, "/resolve-invite", {"invite_code": code})
    assert response.status_code == 200, response.text
    info = response.json()
    consent = info["consent"]
    response = post(
        credits,
        "/join",
        {
            "invite_code": code,
            "consent_id": consent["id"],
            "consent_sha256": consent["sha256"],
            "role": role,
            "adult_confirmed": True,
            "voluntary": True,
            "understood": True,
            "research_permission": True,
            "fixture_confirmed": True,
        },
    )
    assert response.status_code == 200, response.text
    return account, response.json()["member_id"]


def approve(credits, study, member, reference):
    login_owner(credits)
    response = post(
        credits,
        f"/{study}/members/{member}/review",
        {**key(), "approved": True, "verification_reference": reference},
    )
    assert response.status_code == 200, response.text


def login(credits, name):
    response = credits.client.post(
        "/api/v1/auth/login",
        json={"login_identifier": name, "password": PASSWORD},
        headers=csrf_headers(credits.client),
    )
    assert response.status_code == 200, response.text


def photo(credits, study, *, color=90, request_key=None):
    output = BytesIO()
    image = Image.new("RGB", (256, 320), (color, 100, 120))
    image.putpixel((128, 160), (200, 30, 20))
    image.save(output, "PNG")
    meta = {
        "idempotency_key": str(request_key or uuid4()),
        "self_portrait": True,
        "adult_confirmed": True,
        "rights_confirmed": True,
        "fixture_confirmed": True,
        "pose": "frontal",
        "lighting": "diffuse",
    }
    return credits.client.post(
        BASE + f"/{study}/photos",
        content=output.getvalue(),
        headers={
            **csrf_headers(credits.client),
            "Content-Type": "image/png",
            "X-Upload-Metadata": quote(json.dumps(meta)),
        },
    )


def rate(credits, study, value=4):
    response = post(credits, f"/{study}/assignments", key())
    assert response.status_code == 200, response.text
    assignment = response.json()
    assert assignment is not None
    aid = assignment["id"]
    image = credits.client.get(BASE + f"/{study}/assignments/{aid}/content")
    assert image.status_code == 200 and image.headers["cache-control"] == "no-store"
    assert post(credits, f"/{study}/assignments/{aid}/rating", {"score": value}).status_code == 429
    assert post(credits, f"/{study}/assignments/{aid}/view", key()).status_code == 200
    with credits.sessions.begin() as session:
        row = session.get(Assignment, UUID(aid))
        row.viewed_at = now() - timedelta(seconds=3)  # Test clock only, never live data.
    response = post(credits, f"/{study}/assignments/{aid}/rating", {"score": value})
    assert response.status_code == 200, response.text
    return aid


def test_collection_disabled_by_default_and_no_permissions_escalation(credits):
    register(credits.client, "ordinary-study-test")
    assert credits.client.get(BASE + "/status").json()["enabled"] is False
    assert credits.client.get(BASE).json() == []
    assert post(credits, "", {**key(), "title": "Blocked study"}).status_code == 403
    assert credits.client.post(BASE + "/join", json={}).status_code == 403


def test_full_fixture_collection_rating_export_and_withdrawal(credits, tmp_path):
    data = setup(credits, tmp_path)
    study, code = create(credits)
    _, contributor = join(credits, code, "contributor", "fixture-contributor")
    assert photo(credits, study).status_code == 403
    approve(credits, study, contributor, "fixture-person-1")
    login(credits, "fixture-contributor")
    request_key = uuid4()
    response = photo(credits, study, request_key=request_key)
    assert response.status_code == 201, response.text
    photo_id = response.json()["id"]
    assert photo(credits, study, request_key=request_key).json()["id"] == photo_id
    assert photo(credits, study).status_code == 409
    login_owner(credits)
    assert (
        post(
            credits,
            f"/{study}/photos/{photo_id}/review",
            {**key(), "approved": True, "reason": "Authorized generated test fixture"},
        ).status_code
        == 200
    )
    for i in range(3):
        _, member = join(credits, code, "rater", f"fixture-rater-{i}")
        approve(credits, study, member, f"fixture-independent-{i}")
        login(credits, f"fixture-rater-{i}")
        aid = rate(credits, study, 3 + i)
        assert (
            post(credits, f"/{study}/assignments/{aid}/rating", {"score": 3 + i}).status_code == 200
        )
        assert post(credits, f"/{study}/assignments/{aid}/rating", {"score": 1}).status_code == 409
        assert post(credits, f"/{study}/assignments", key()).json() is None
    login_owner(credits)
    assert act(credits, study, "close").status_code == 200
    response = post(credits, f"/{study}/exports", key())
    assert response.status_code == 201, response.text
    export = response.json()["id"]
    archive = credits.client.get(BASE + f"/{study}/exports/{export}/content")
    assert archive.status_code == 200
    root = tmp_path / "export"
    with ZipFile(BytesIO(archive.content)) as zipfile:
        zipfile.extractall(root)  # Server-generated fixture archive only.
    plan = Collection.model_validate_json((root / "collection.json").read_bytes())
    assert plan.synthetic and plan.rating_max == 7
    payloads, subjects, labels, _, _ = load_rows(root / "means.csv", root, plan)
    assert len(payloads) == len(set(subjects)) == 1 and labels.tolist() == [4.0]
    assert len(list(csv.DictReader((root / "annotations.csv").open()))) == 3
    # One portrait cannot identify rater offsets: the adjusted label equals the plain mean.
    adjusted, *_ = load_rows(root / "adjusted.csv", root, plan)[2:3]
    assert adjusted.tolist() == [4.0]
    quality = json.loads((root / "reliability.json").read_text())
    assert quality["agreement"]["status"] == "insufficient_data"
    assert quality["rater_model"]["adjusted"] is False
    assert "fixture-rater" not in archive.content.decode("latin1")
    import hashlib

    manifest = json.loads((root / "manifest.json").read_text())
    assert not manifest["independent_external_holdout"]
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    assert len(json.loads((root / "receipts.json").read_text())) == 4
    for digest, policy in json.loads((root / "consents.json").read_text()).items():
        if digest.startswith("consent-"):
            continue
        assert (
            hashlib.sha256(
                json.dumps(policy, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            == digest
        )
    from aevyra_api.studies.models import StudyExport

    with credits.sessions.begin() as session:
        row = session.get(StudyExport, UUID(export))
        original_digest = row.sha256
        row.sha256 = "0" * 64
    assert credits.client.get(BASE + f"/{study}/exports/{export}/content").status_code == 503
    with credits.sessions.begin() as session:
        session.get(StudyExport, UUID(export)).sha256 = original_digest

    login(credits, "fixture-contributor")
    receipt = credits.client.get(BASE + f"/{study}/receipts")
    assert receipt.status_code == 200 and len(receipt.json()) == 1
    assert post(credits, f"/{study}/withdraw", key()).status_code == 200
    assert post(credits, f"/{study}/withdraw", key()).status_code == 200
    login_owner(credits)
    assert credits.client.get(BASE + f"/{study}/exports/{export}/content").status_code == 410
    with credits.sessions() as session:
        assert session.get(Photo, UUID(photo_id)).artifact_id is None
        assert (
            session.scalar(
                select(func.count()).select_from(Assignment).where(Assignment.score.is_not(None))
            )
            == 0
        )
    assert not list(data.export_store().root.rglob("*/*"))


def test_consent_is_immutable_and_old_acceptance_cannot_authorize_new_work(credits, tmp_path):
    setup(credits, tmp_path)
    study, code = create(credits)
    _, member = join(credits, code, "rater", "fixture-consent-rater")
    approve(credits, study, member, "fixture-consent-person")
    assert (
        post(
            credits,
            f"/{study}/consent",
            {
                **key(),
                "text_en": TEXT_EN + " Version 2.",
                "text_zh": TEXT_ZH + " 第二版。",
                "contact_en": "Fixture operator",
                "contact_zh": "测试负责人",
                "rights_reference": "fixture-v2",
            },
        ).status_code
        == 200
    )
    assert act(credits, study, "open").status_code == 200
    login(credits, "fixture-consent-rater")
    assert post(credits, f"/{study}/assignments", key()).status_code == 409
    with pytest.raises(DBAPIError), credits.sessions.begin() as session:
        session.execute(text("UPDATE collection_consent_versions SET text_en='changed'"))
    with pytest.raises(DBAPIError), credits.sessions.begin() as session:
        session.execute(text("DELETE FROM collection_receipts"))
    with pytest.raises(DBAPIError), credits.sessions.begin() as session:
        session.execute(text("UPDATE collection_people SET partition='holdout'"))


def test_holdout_custody_partition_and_seal_are_not_owner_overrides(credits, tmp_path):
    setup(credits, tmp_path)
    custodian = register(credits.client, "fixture-holdout-custodian")
    login_owner(credits)
    development, dev_code = create(credits)
    study, code = create(credits, partition="holdout", custodian=custodian["public_user_id"])
    assert act(credits, study, "open").status_code == 409
    login(credits, "fixture-holdout-custodian")
    consent = post(credits, "/resolve-invite", {"invite_code": code}).json()["consent"]
    assert (
        post(
            credits,
            "/join",
            {
                "invite_code": code,
                "consent_id": consent["id"],
                "consent_sha256": consent["sha256"],
                "role": "custodian",
                "adult_confirmed": True,
                "voluntary": True,
                "understood": True,
                "research_permission": True,
                "fixture_confirmed": True,
            },
        ).status_code
        == 200
    )
    login_owner(credits)
    assert act(credits, study, "open").status_code == 200
    _, contributor = join(credits, code, "contributor", "fixture-heldout-person")
    login(credits, "fixture-holdout-custodian")
    assert (
        post(
            credits,
            f"/{study}/members/{contributor}/review",
            {**key(), "approved": True, "verification_reference": "fixture-heldout-person-proof"},
        ).status_code
        == 200
    )
    login(credits, "fixture-heldout-person")
    photo_id = photo(credits, study).json()["id"]
    # A holdout person can never move to development, even through a separate study.
    dev_consent = post(credits, "/resolve-invite", {"invite_code": dev_code}).json()["consent"]
    assert (
        post(
            credits,
            "/join",
            {
                "invite_code": dev_code,
                "consent_id": dev_consent["id"],
                "consent_sha256": dev_consent["sha256"],
                "role": "rater",
                "adult_confirmed": True,
                "voluntary": True,
                "understood": True,
                "research_permission": True,
                "fixture_confirmed": True,
            },
        ).status_code
        == 409
    )
    login_owner(credits)
    info = credits.client.get(BASE + f"/{study}").json()
    assert info["photos"] == [] and info["members"] == [] and info["can_manage"] is False
    assert credits.client.get(BASE + f"/{study}/photos/{photo_id}/content").status_code == 403
    assert credits.client.get(BASE + f"/{study}/audit").status_code == 403
    assert credits.client.get(BASE + f"/{study}/quality").status_code == 403
    assert post(credits, f"/{study}/exports", key()).status_code == 403
    login(credits, "fixture-holdout-custodian")
    assert (
        post(
            credits,
            f"/{study}/photos/{photo_id}/review",
            {
                **key(),
                "approved": True,
                "reason": "Authorized synthetic fixture and consent verified",
            },
        ).status_code
        == 200
    )
    for i in range(3):
        _, member = join(credits, code, "rater", f"fixture-holdout-rater-{i}")
        login(credits, "fixture-holdout-custodian")
        assert (
            post(
                credits,
                f"/{study}/members/{member}/review",
                {
                    **key(),
                    "approved": True,
                    "verification_reference": f"fixture-holdout-independent-{i}",
                },
            ).status_code
            == 200
        )
        login(credits, f"fixture-holdout-rater-{i}")
        rate(credits, study, i + 4)
    login_owner(credits)
    assert act(credits, study, "close").status_code == 200
    assert act(credits, study, "seal").status_code == 403
    login(credits, "fixture-holdout-custodian")
    sealed = act(credits, study, "seal")
    assert sealed.status_code == 200 and len(sealed.json()["value"]) == 64
    login_owner(credits)
    assert act(credits, study, "open").status_code == 409
    assert post(credits, f"/{study}/exports", key()).status_code == 403
    login(credits, "fixture-heldout-person")
    credits.client.app.state.settings.study_collection_enabled = False
    assert post(credits, f"/{study}/withdraw", key()).status_code == 200
    assert credits.client.get(BASE + f"/{study}/receipts").status_code == 200
    assert credits.client.get(BASE + f"/{study}").json()["memberships"][0]["active"] is False
    with credits.sessions() as session:
        snapshot = session.get(Study, UUID(study))
        assert snapshot.seal_sha256 is None and snapshot.sealed_at is not None
        # Participant user IDs never enter the Owner-visible administrative audit.
        from aevyra_api.admin_models import AdminAudit
        from aevyra_api.credits.models import User

        actor = session.scalar(
            select(User.id).where(User.login_identifier == "fixture-heldout-person")
        )
        assert not session.scalar(select(AdminAudit.id).where(AdminAudit.actor_id == actor))
    credits.client.app.state.settings.study_collection_enabled = True
    login(credits, "fixture-holdout-custodian")
    assert act(credits, study, "seal").status_code == 409


def test_withdrawal_fences_access_even_if_unlink_fails_and_worker_retries(
    credits, tmp_path, monkeypatch
):
    from aevyra_api.research.storage import PrivateArtifactStore
    from aevyra_api.studies.models import StudyGarbage

    data = setup(credits, tmp_path)
    study, code = create(credits)
    _, member = join(credits, code, "contributor", "fixture-erasure-person")
    approve(credits, study, member, "fixture-erasure-proof")
    login(credits, "fixture-erasure-person")
    photo_id = photo(credits, study).json()["id"]
    real_delete = PrivateArtifactStore.delete

    def denied(*args):
        raise PermissionError("fixture erasure error")

    monkeypatch.setattr(PrivateArtifactStore, "delete", denied)
    response = post(credits, f"/{study}/withdraw", key())
    assert response.status_code == 200 and response.json()["cleanup_pending"] is True
    with credits.sessions() as session:
        assert session.get(Photo, UUID(photo_id)).artifact_id is None
        assert session.scalar(select(func.count()).select_from(StudyGarbage)) == 1
    assert len(list((data.settings.private_upload_root / "study-development").rglob("*/*"))) == 1
    login_owner(credits)
    assert credits.client.get(BASE + f"/{study}/photos/{photo_id}/content").status_code == 404
    monkeypatch.setattr(PrivateArtifactStore, "delete", real_delete)
    data.settings.study_collection_enabled = False
    data.purge()
    assert not list((data.settings.private_upload_root / "study-development").rglob("*/*"))
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(StudyGarbage)) == 0


def test_identity_proof_prevents_duplicate_accounts_and_self_ratings(credits, tmp_path):
    setup(credits, tmp_path)
    study, code = create(credits)
    _, first = join(credits, code, "contributor", "fixture-identity-one")
    approve(credits, study, first, "fixture-stable-proof")
    _, second = join(credits, code, "rater", "fixture-identity-two")
    login_owner(credits)
    assert (
        post(
            credits,
            f"/{study}/members/{second}/review",
            {**key(), "approved": True, "verification_reference": "fixture-stable-proof"},
        ).status_code
        == 409
    )
    login(credits, "fixture-identity-one")
    consent = post(credits, "/resolve-invite", {"invite_code": code}).json()["consent"]
    response = post(
        credits,
        "/join",
        {
            "invite_code": code,
            "consent_id": consent["id"],
            "consent_sha256": consent["sha256"],
            "role": "rater",
            "adult_confirmed": True,
            "voluntary": True,
            "understood": True,
            "research_permission": True,
            "fixture_confirmed": True,
        },
    )
    own_rater = response.json()["member_id"]
    own_photo = photo(credits, study).json()["id"]
    approve(credits, study, own_rater, "fixture-stable-proof")
    assert (
        post(
            credits,
            f"/{study}/photos/{own_photo}/review",
            {**key(), "approved": True, "reason": "Authorized fixture"},
        ).status_code
        == 200
    )
    login(credits, "fixture-identity-one")
    assert post(credits, f"/{study}/assignments", key()).json() is None


def test_blind_repeats_are_separate_from_primary_votes(credits, tmp_path):
    setup(credits, tmp_path)
    study, code = create(credits)
    _, member = join(credits, code, "contributor", "fixture-repeat-source")
    approve(credits, study, member, "fixture-repeat-source-proof")
    login(credits, "fixture-repeat-source")
    photos = [photo(credits, study, color=30 + i * 20).json()["id"] for i in range(6)]
    login_owner(credits)
    for item in photos:
        assert (
            post(
                credits,
                f"/{study}/photos/{item}/review",
                {**key(), "approved": True, "reason": "Authorized generated fixture"},
            ).status_code
            == 200
        )
    _, rater = join(credits, code, "rater", "fixture-repeat-rater")
    approve(credits, study, rater, "fixture-repeat-rater-proof")
    login(credits, "fixture-repeat-rater")
    for _ in range(7):
        assignment = post(credits, f"/{study}/assignments", key()).json()
        assert "repeat" not in assignment  # Do not reveal which assignments are quality checks.
        assert post(credits, f"/{study}/assignments", key()).json()["id"] == assignment["id"]
        aid = assignment["id"]
        assert post(credits, f"/{study}/assignments/{aid}/rating", {"score": 8}).status_code == 422
        assert post(credits, f"/{study}/assignments/{aid}/view", key()).status_code == 200
        with credits.sessions.begin() as session:
            session.get(Assignment, UUID(aid)).viewed_at = now() - timedelta(seconds=3)
        assert post(credits, f"/{study}/assignments/{aid}/rating", {"score": 7}).status_code == 200
    assert post(credits, f"/{study}/assignments", key()).json() is None
    login_owner(credits)
    quality = credits.client.get(BASE + f"/{study}/quality").json()[0]
    assert quality["primary_ratings"] == 6 and quality["repeat_checks"] == 1
    assert quality["automatic_exclusion"] is False


def test_retention_integrity_and_disabled_withdrawal(credits, tmp_path):
    data = setup(credits, tmp_path)
    study, code = create(credits)
    _, member = join(credits, code, "contributor", "fixture-retention-subject")
    approve(credits, study, member, "fixture-retention-proof")
    login(credits, "fixture-retention-subject")
    response = photo(credits, study)
    assert response.status_code == 201
    photo_id = UUID(response.json()["id"])
    with credits.sessions() as session:
        row = session.get(Photo, photo_id)
        artifact = row.artifact_id
        store = data.store(session.get(Study, UUID(study)))
    assert credits.client.get(BASE + f"/{study}/photos/{photo_id}/content").status_code == 200
    path = store.root / study / str(artifact)
    path.write_bytes(b"corrupt authorized fixture")
    assert credits.client.get(BASE + f"/{study}/photos/{photo_id}/content").status_code == 503
    with credits.sessions.begin() as session:
        session.get(Photo, photo_id).expires_at = now() - timedelta(seconds=1)
    assert credits.client.get(BASE + f"/{study}/photos/{photo_id}/content").status_code == 404
    data.settings.study_collection_enabled = False
    data.purge()
    assert not path.exists()
    assert credits.client.get(BASE + f"/{study}/receipts").status_code == 200
    assert post(credits, f"/{study}/withdraw", key()).status_code == 200
    assert credits.client.get("/api/v1/account").json()["wallet"]["balance"] == 0


def test_approval_proof_cannot_be_silently_reassigned(credits, tmp_path):
    setup(credits, tmp_path)
    study, code = create(credits)
    join(credits, code, "rater", "fixture-proof-guard")
    with credits.sessions.begin() as session:
        from aevyra_api.studies.models import Person

        person = session.scalar(select(Person))
        person.identity_digest = "a" * 64
    with pytest.raises(DBAPIError), credits.sessions.begin() as session:
        session.execute(text("UPDATE collection_people SET identity_digest=NULL"))


@pytest.mark.integration
def test_postgres_duplicate_assignment_and_evidence_guards(tmp_path):
    """Fresh randomized schema only; verify real row locks, indexes and trigger SQL."""
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from aevyra_api.accounts import COOKIE
    from aevyra_api.config import Settings
    from aevyra_api.main import create_app
    from fastapi.testclient import TestClient
    from test_credits import TestLimiter
    from test_postgres_commercial import postgres_services

    with postgres_services() as (sessions, _, _, _):
        settings = Settings(api_environment="test", _env_file=None)
        application = create_app(settings)
        application.state.sessions = sessions
        application.state.settings = settings
        application.state.rate_limiter = TestLimiter()
        fixture = SimpleNamespace(client=TestClient(application), sessions=sessions)
        data = setup(fixture, tmp_path)
        study, code = create(fixture)
        _, member = join(fixture, code, "contributor", "fixture-pg-subject")
        approve(fixture, study, member, "fixture-pg-proof")
        login(fixture, "fixture-pg-subject")
        photo_id = photo(fixture, study).json()["id"]
        login_owner(fixture)
        assert (
            post(
                fixture,
                f"/{study}/photos/{photo_id}/review",
                {**key(), "approved": True, "reason": "Authorized PostgreSQL test fixture"},
            ).status_code
            == 200
        )
        _, rater = join(fixture, code, "rater", "fixture-pg-rater")
        approve(fixture, study, rater, "fixture-pg-rater-proof")
        login(fixture, "fixture-pg-rater")
        token = fixture.client.cookies.get(COOKIE)
        from aevyra_api.accounts import AccountService

        user = AccountService(sessions, settings).authenticate(token)
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda _: data.assignment(user.id, UUID(study)).id, range(4)))
        assert len(set(ids)) == 1
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(Assignment)) == 1
        with pytest.raises(DBAPIError), sessions.begin() as session:
            session.execute(text("UPDATE collection_people SET partition='holdout'"))
        with pytest.raises(DBAPIError), sessions.begin() as session:
            session.execute(text("TRUNCATE collection_audit"))
        with pytest.raises(DBAPIError), sessions.begin() as session:
            session.execute(text("DELETE FROM collection_receipts"))
        fixture.client.close()


def test_portrait_deletion_is_idempotent_without_touching_other_research(credits, tmp_path):
    setup(credits, tmp_path)
    study, code = create(credits)
    _, member = join(credits, code, "contributor", "fixture-delete-subject")
    approve(credits, study, member, "fixture-delete-subject-proof")
    login(credits, "fixture-delete-subject")
    photo_id = photo(credits, study).json()["id"]
    payload = key()
    assert post(credits, f"/{study}/photos/{photo_id}/delete", payload).status_code == 200
    revision = credits.client.get(BASE + f"/{study}").json()["revision"]
    assert post(credits, f"/{study}/photos/{photo_id}/delete", payload).status_code == 200
    assert credits.client.get(BASE + f"/{study}").json()["revision"] == revision
    assert post(credits, f"/{study}/withdraw", payload).status_code == 409


def test_assignment_fills_least_covered_portraits_first(credits, tmp_path):
    setup(credits, tmp_path)
    study, code = create(credits)
    _, contributor = join(credits, code, "contributor", "balance-contributor")
    approve(credits, study, contributor, "balance-person-1")
    login(credits, "balance-contributor")
    photos = [photo(credits, study, color=40 + 30 * i).json()["id"] for i in range(4)]
    login_owner(credits)
    for photo_id in photos:
        response = post(
            credits,
            f"/{study}/photos/{photo_id}/review",
            {**key(), "approved": True, "reason": "Authorized generated test fixture"},
        )
        assert response.status_code == 200, response.text
    seen: dict[str, list[str]] = {}
    for name in ("balance-rater-a", "balance-rater-b", "balance-rater-c"):
        _, member = join(credits, code, "rater", name)
        approve(credits, study, member, name + "-proof")
        login(credits, name)
        seen[name] = []
        for _ in range(2):
            with credits.sessions() as session:
                aid = rate(credits, study)
                seen[name].append(str(session.get(Assignment, UUID(aid)).photo_id))
    # Rater B must first cover the two portraits rater A never saw; C then fills the rest.
    assert set(seen["balance-rater-b"]) == set(photos) - set(seen["balance-rater-a"])
    with credits.sessions() as session:
        counts = [
            session.scalar(
                select(func.count())
                .select_from(Assignment)
                .where(Assignment.photo_id == UUID(p), Assignment.status == "SAVED")
            )
            for p in photos
        ]
    assert sorted(counts) == [1, 1, 2, 2]
