from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from aevyra_api.accounts import COOKIE, HASHER, AccountService
from aevyra_api.admin_models import FreeAnalysisGrant
from aevyra_api.commercial.models import Analysis, now
from aevyra_api.commercial.state import DomainError
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.models import AccountSession, CreditTransaction, User, Wallet
from aevyra_api.entitlements import product_access, research_limits
from aevyra_api.owner import main, provision, rotate
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess, ResearchJob
from aevyra_inference.engine import EngineRegistry
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError
from test_credits import PASSWORD, csrf_headers, register, run_analysis
from test_credits import credits as credits

OWNER_PASSWORD = "synthetic-owner-test-password-only"


def login_owner(credits):
    response = credits.client.post(
        "/api/v1/auth/login",
        json={"login_identifier": "owner_god", "password": OWNER_PASSWORD},
        headers=csrf_headers(credits.client),
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def owner(credits):
    provision(credits.sessions, OWNER_PASSWORD)
    return login_owner(credits)


def post(fixture, path, **body):
    return fixture.client.post(
        "/api/v1/owner" + path,
        json={"idempotency_key": str(uuid4()), "reason": "Synthetic test operation", **body},
        headers=csrf_headers(fixture.client),
    )


def test_owner_bootstrap_reserved_identifier_and_no_escalation(credits):
    for name in ("owner_god", "OWNER_GOD", " owner_god "):
        result = credits.client.post(
            "/api/v1/auth/register",
            json={"login_identifier": name, "password": PASSWORD},
            headers=csrf_headers(credits.client),
        )
        assert result.status_code in (409, 422)
    register(credits.client, "ordinary")
    assert credits.client.get("/api/v1/owner/users").status_code == 403
    assert post(credits, "/batches", name="Attack", quantity=1, credits=10).status_code == 403
    assert (
        credits.client.post(
            "/api/v1/auth/register",
            json={"login_identifier": "attacker", "password": PASSWORD, "role": "owner"},
            headers=csrf_headers(credits.client),
        ).status_code
        == 422
    )
    user = owner(credits)
    assert user["role"] == "owner"
    with credits.sessions() as session:
        stored = session.scalar(select(User).where(User.role == "owner"))
        before = stored.password_hash
        assert before.startswith("$argon2id$") and HASHER.verify(before, OWNER_PASSWORD)
        assert session.scalar(select(func.count()).select_from(Wallet)) == 2
    with pytest.raises(ValueError, match="already exists"):
        provision(credits.sessions, "another-unused-secret")
    with credits.sessions() as session:
        assert session.scalar(select(User.password_hash).where(User.role == "owner")) == before
    assert credits.client.get("/api/v1/owner/users").status_code == 200
    assert credits.client.get("/api/v1/owner/users").headers["cache-control"] == "no-store"


def test_owner_identity_database_guards(credits):
    owner(credits)
    register(credits.client, "ordinary")
    for sql in (
        "UPDATE users SET role='owner' WHERE login_identifier='ordinary'",
        "UPDATE users SET role='user' WHERE role='owner'",
        "UPDATE users SET disabled_at=CURRENT_TIMESTAMP WHERE role='owner'",
        "UPDATE users SET login_identifier='renamed' WHERE role='owner'",
        "DELETE FROM users WHERE role='owner'",
        "UPDATE users SET role='admin' WHERE role='user'",
    ):
        with pytest.raises(DBAPIError), credits.sessions.begin() as session:
            session.execute(text(sql))


def test_owner_password_rotation_recovery_revoke_sessions_and_expiry(credits):
    owner(credits)
    token = credits.client.cookies.get(COOKIE)
    with pytest.raises(ValueError, match="incorrect"):
        rotate(credits.sessions, "new-synthetic-password", current_password="wrong")
    with pytest.raises(ValueError, match="explicit"):
        rotate(credits.sessions, "new-synthetic-password", recovery_confirmation="owner_god")
    rotate(credits.sessions, "new-synthetic-password", current_password=OWNER_PASSWORD)
    assert credits.client.get("/api/v1/owner/users").status_code == 401
    account = AccountService(credits.sessions, credits.client.app.state.settings)
    with pytest.raises(DomainError):
        account.login("owner_god", OWNER_PASSWORD)
    user, new_token = account.login("owner_god", "new-synthetic-password")
    assert new_token != token
    rotate(
        credits.sessions,
        "recovered-synthetic-password",
        recovery_confirmation=f"RECOVER {user.public_user_id}",
    )
    with pytest.raises(DomainError):
        account.authenticate(new_token)
    _, new_token = account.login("owner_god", "recovered-synthetic-password")
    with credits.sessions.begin() as session:
        session.scalar(select(AccountSession)).expires_at = now() - timedelta(seconds=1)
    with pytest.raises(DomainError):
        account.authenticate(new_token)
    with (
        patch("sys.argv", ["owner"]),
        patch("sys.stdin.isatty", return_value=False),
        pytest.raises(SystemExit, match="interactive"),
    ):
        main()


def test_free_analysis_durable_funding_idempotency_failure_and_production(credits):
    owner(credits)
    key = str(uuid4())
    first = run_analysis(credits, key)
    assert first.status_code == 200
    assert run_analysis(credits, key).json()["id"] == first.json()["id"]
    assert run_analysis(credits, key, product_slug="different-product").status_code == 409
    credits.engine.fail = True
    failed = run_analysis(credits).json()
    assert failed["status"] == "FAILED"
    assert "no Credits charged" in failed["failure_reason"]
    service = CreditAnalysisService(
        credits.sessions, EngineRegistry([credits.engine]), production=False
    )
    for _ in range(3):
        service.refund_failed(UUID(failed["id"]))
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(FreeAnalysisGrant)) == 2
        assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 0
        assert session.scalar(select(Wallet.cached_balance)) == 0
    credits.client.app.state.settings.api_environment = "production"
    assert run_analysis(credits).status_code == 404
    # Missing debit without a recorded free grant is never forgiven just because of role.
    with credits.sessions.begin() as session:
        user_id = session.scalar(select(User.id))
        unbacked = Analysis(
            user_id=user_id,
            credit_request_key="unbacked",
            scoring_engine_slug="mock",
            status="FAILED",
        )
        session.add(unbacked)
        session.flush()
        unbacked_id = unbacked.id
    with pytest.raises(DomainError, match="reconciliation"):
        service.refund_failed(unbacked_id)


def test_admin_csrf_session_forgery_and_fresh_auth(credits):
    target = register(credits.client)
    owner(credits)
    path = "/users/" + target["public_user_id"] + "/credits"
    body = {"amount": 20, "reason": "Synthetic test", "idempotency_key": str(uuid4())}
    assert credits.client.post("/api/v1/owner" + path, json=body).status_code == 403
    assert (
        credits.client.post(
            "/api/v1/owner" + path,
            json=body,
            headers={**csrf_headers(credits.client), "Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert post(credits, path, **body, role="owner").status_code == 422
    with credits.sessions.begin() as session:
        for stored in session.scalars(select(AccountSession)):
            stored.created_at = now() - timedelta(minutes=11)
    assert post(credits, path, **body).status_code == 403
    login_owner(credits)
    assert post(credits, path, **body).status_code == 200
    credits.client.cookies.clear()
    credits.client.cookies.set(COOKIE, "owner_god")
    assert credits.client.get("/api/v1/owner/audit").status_code == 401


def test_user_admin_grants_disable_restore_and_ledger(credits):
    target = register(credits.client)
    ordinary_token = credits.client.cookies.get(COOKIE)
    own = owner(credits)
    prefix = "/users/" + target["public_user_id"]
    key = str(uuid4())
    first = post(credits, prefix + "/credits", amount=25, idempotency_key=key)
    assert first.status_code == 200
    assert post(credits, prefix + "/credits", amount=25, idempotency_key=key).json() == first.json()
    assert post(credits, prefix + "/credits", amount=26, idempotency_key=key).status_code == 409
    assert post(credits, prefix + "/credits", amount=-1).status_code == 422
    ledger = credits.client.get("/api/v1/owner" + prefix + "/credits").json()["data"]
    assert ledger["reconciled"] and ledger["ledger_balance"] == 25 and ledger["total"] == 1
    assert post(credits, prefix + "/research", enabled=True).status_code == 200
    assert post(credits, prefix + "/status", disabled=True).status_code == 200
    assert post(credits, prefix + "/status", disabled=False).status_code == 200
    with pytest.raises(DomainError):
        AccountService(credits.sessions, credits.client.app.state.settings).authenticate(
            ordinary_token
        )
    assert post(credits, prefix + "/research", enabled=False).status_code == 200
    for suffix, values in (
        ("/status", {"disabled": True}),
        ("/research", {"enabled": False}),
        ("/credits", {"amount": 1}),
    ):
        assert (
            post(credits, "/users/" + own["public_user_id"] + suffix, **values).status_code == 403
        )
    listing = credits.client.get("/api/v1/owner/users?search=pilot&page_size=1").json()
    assert listing["total"] == 1 and listing["items"][0]["balance"] == 25
    assert "password_hash" not in str(listing) and "token" not in str(listing)
    audits = credits.client.get("/api/v1/owner/audit").json()["items"]
    assert any(a["outcome"] == "failure" for a in audits)
    assert len([a for a in audits if a["action"] == "credits.grant"]) == 1
    for table in ("admin_audit", "free_analysis_grants"):
        for verb in ("DELETE FROM", "UPDATE"):
            sql = (
                f"{verb} {table}"
                + (
                    " SET policy='changed'"
                    if table == "free_analysis_grants"
                    else " SET target='changed'"
                )
                if verb == "UPDATE"
                else f"{verb} {table}"
            )
            if table == "admin_audit":
                with pytest.raises(DBAPIError), credits.sessions.begin() as session:
                    session.execute(text(sql))


def test_redemption_one_time_export_audit_redaction_and_disable(credits):
    target = register(credits.client)
    owner(credits)
    body = {
        "name": "Synthetic campaign",
        "quantity": 3,
        "credits": 7,
        "idempotency_key": str(uuid4()),
    }
    created = post(credits, "/batches", **body)
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert len(data["codes"]) == 3
    assert post(credits, "/batches", **body).status_code == 409
    for route in ("/batches", "/audit", "/users"):
        response = credits.client.get("/api/v1/owner" + route)
        assert all(code not in response.text for code in data["codes"])
        assert "lookup_digest" not in response.text
    from aevyra_api.accounts import pepper
    from aevyra_api.credits.codes import redeem

    with credits.sessions() as session:
        uid = session.scalar(select(User.id).where(User.public_user_id == target["public_user_id"]))
    assert redeem(
        credits.sessions, pepper(credits.client.app.state.settings), uid, data["codes"][0]
    ) == (7, 7)
    assert credits.client.get("/api/v1/owner/batches").json()["items"][0]["redeemed"] == 1
    assert post(credits, "/batches/" + data["public_batch_id"] + "/disable").status_code == 200
    with pytest.raises(DomainError):
        redeem(credits.sessions, pepper(credits.client.app.state.settings), uid, data["codes"][1])


def test_owner_research_policy_limits_isolation_and_unavailable_provider(credits, tmp_path):
    owner(credits)
    settings = credits.client.app.state.settings
    settings.research_mode = True
    settings.private_upload_root = tmp_path / "uploads"
    settings.private_model_root = tmp_path / "models"
    with credits.sessions.begin() as session:
        uid = session.scalar(select(User.id))
        session.execute(delete(ResearchAccess))
        limits = research_limits(session, uid, settings)
        assert limits.images == 1000 and limits.pending == 4
        stored = session.get(User, uid)
        assert product_access(stored, standard_allowed=False)
    assert credits.client.get("/api/v1/research/status").json()["authorized"]
    data = PreferenceService(credits.sessions, settings)
    for i in range(21):
        data.create_project(uid, f"Owner project {i}")
    queue = ResearchQueue(credits.sessions, settings)
    with pytest.raises(DomainError, match="unavailable"):
        queue.enqueue(uid, "comboloss", str(uuid4()))
    for _ in range(4):
        queue.enqueue(uid, "mock", str(uuid4()))
    with pytest.raises(DomainError, match="limit"):
        queue.enqueue(uid, "mock", str(uuid4()))
    assert queue.claim() is not None and queue.claim() is None
    # Summary includes only scheduling metadata, never user-provided payload/results.
    with credits.sessions.begin() as session:
        job = session.scalar(select(ResearchJob))
        job.payload = {"private": "NEVER_EXPOSE_THIS"}
        job.result = {"secret": "NEVER_EXPOSE_THIS"}
    response = credits.client.get("/api/v1/owner/jobs")
    assert response.status_code == 200 and "NEVER_EXPOSE_THIS" not in response.text
    settings.research_mode = False
    assert not credits.client.get("/api/v1/research/status").json()["authorized"]


def test_owner_never_bypasses_private_dataset_or_model_ownership(credits):
    from test_custom_training import execute, models, populated, train_job
    from test_preferences import BASE, upload
    from test_preferences import post as preference_post

    dataset = populated(credits)
    train_job(credits, dataset)
    execute(credits)
    model = models(credits)[0]
    image = upload(credits, dataset, "blue").json()
    owner(credits)
    assert credits.client.get(BASE + f"/datasets/{dataset}").status_code == 404
    assert (
        credits.client.get(BASE + f"/datasets/{dataset}/images/{image['id']}/content").status_code
        == 404
    )
    assert (
        preference_post(
            credits, "/train", {"dataset_id": dataset, "idempotency_key": str(uuid4())}
        ).status_code
        == 404
    )
    assert (
        preference_post(
            credits,
            "/predict",
            {
                "dataset_id": dataset,
                "image_id": image["id"],
                "model_id": model["id"],
                "idempotency_key": str(uuid4()),
            },
        ).status_code
        == 404
    )
    assert models(credits) == []


@pytest.mark.pretrained
def test_owner_actual_pretrained_training_prediction_without_access_record(
    credits, pretrained_root
):
    import shutil

    from aevyra_inference.extractors import MOBILENET, WEIGHT_FILE
    from test_custom_training import execute, models, train_job
    from test_preferences import BASE, upload
    from test_preferences import post as preference_post

    owner(credits)
    settings = credits.client.app.state.settings
    settings.research_mode = True
    from pathlib import Path

    settings.private_upload_root = Path.cwd() / "private"
    settings.private_model_root = Path.cwd() / "models"
    target = settings.private_model_root / "pretrained"
    target.mkdir(parents=True)
    shutil.copyfile(pretrained_root / WEIGHT_FILE, target / WEIGHT_FILE)
    with credits.sessions.begin() as session:
        session.execute(delete(ResearchAccess))
    project = preference_post(credits, "/projects", {"name": "Owner numerical preferences"}).json()
    dataset = preference_post(
        credits,
        "/datasets",
        {
            "project_id": project["id"],
            "name": "Synthetic owner dataset",
            "source": "Generated colors",
            "license": "Software fixture",
            "adult_authorized_consent": True,
        },
    ).json()["id"]
    for i in range(10):
        image = upload(
            credits, dataset, (20 + i * 20, 40, 50), subject_group=f"synthetic-{i}"
        ).json()
        assert (
            preference_post(
                credits, f"/datasets/{dataset}/images/{image['id']}/rating", {"score": 1 + i * 0.8}
            ).status_code
            == 200
        )
    train_job(credits, dataset, extractor=MOBILENET)
    execute(credits)
    model = models(credits)[0]
    assert model["state"] == "READY"
    image = upload(credits, dataset, (125, 40, 50)).json()
    job = preference_post(
        credits,
        "/predict",
        {
            "dataset_id": dataset,
            "image_id": image["id"],
            "model_id": model["id"],
            "idempotency_key": str(uuid4()),
        },
    ).json()
    execute(credits)
    result = credits.client.get("/api/v1/research/jobs/" + job["id"]).json()
    assert result["status"] == "COMPLETED" and not result["result"]["seen_in_training_snapshot"]
    assert result["result"]["synthetic"] is False
    assert credits.client.get(BASE + "/models").json()[0]["id"] == model["id"]
    assert credits.client.get("/api/v1/account").json()["wallet"] == {
        "balance": 0,
        "transactions": [],
    }

    # Metadata fixture: 300 retained versions must remain manageable after deletions.
    # This tests listing, not the cost/accuracy of training 300 separate models.
    from aevyra_api.preferences.training_models import CustomModel

    with credits.sessions.begin() as session:
        original = session.get(CustomModel, UUID(model["id"]))
        values = {
            column.key: getattr(original, column.key)
            for column in CustomModel.__table__.columns
            if column.key not in {"id", "version", "training_job_id", "created_at", "state"}
        }
        for version in range(2, 506):
            job = ResearchJob(
                user_id=original.user_id,
                request_key=f"listing-{version}",
                provider="custom",
                kind="TRAIN",
                status="COMPLETED",
            )
            session.add(job)
            session.flush()
            session.add(
                CustomModel(
                    **values,
                    version=version,
                    training_job_id=job.id,
                    state="READY" if version <= 300 else "DELETED",
                )
            )
    listed = models(credits)
    assert len(listed) == 400
    assert len([item for item in listed if item["state"] == "READY"]) == 300
    assert model["id"] in {item["id"] for item in listed}


def test_admin_revocation_fences_queued_and_running_work(credits):
    from test_research import enable

    target = register(credits.client)
    enable(credits)
    with credits.sessions() as session:
        uid = session.scalar(select(User.id))
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    queue.enqueue(uid, "mock", "first")
    queue.enqueue(uid, "mock", "second")
    lease = queue.claim()
    owner(credits)
    assert (
        post(credits, "/users/" + target["public_user_id"] + "/research", enabled=False).status_code
        == 200
    )
    assert queue.renew(lease) is False and queue.finish(lease, {"synthetic": True}) is False
    assert (
        post(credits, "/users/" + target["public_user_id"] + "/research", enabled=True).status_code
        == 200
    )
    assert queue.claim() is None
    with credits.sessions() as session:
        assert all(
            job.status == "FAILED" and job.lease_token is None
            for job in session.scalars(select(ResearchJob))
        )


def test_occupied_reserved_login_cannot_be_hijacked_by_bootstrap(credits):
    # Simulate an account predating the public-registration reservation.
    with credits.sessions.begin() as session:
        user = User(
            public_user_id="usr_" + uuid4().hex,
            login_identifier="owner_god",
            password_hash=HASHER.hash(PASSWORD),
        )
        session.add(user)
        session.flush()
        session.add(Wallet(user_id=user.id))
    with pytest.raises(ValueError, match="occupied"):
        provision(credits.sessions, OWNER_PASSWORD)
    user, _ = AccountService(credits.sessions, credits.client.app.state.settings).login(
        "owner_god", PASSWORD
    )
    assert user.role == "user"
