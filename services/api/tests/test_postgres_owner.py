from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from aevyra_api.accounts import HASHER, AccountService, session_digest
from aevyra_api.admin_models import AdminAudit, FreeAnalysisGrant
from aevyra_api.administration import Administration
from aevyra_api.commercial.models import Analysis, now
from aevyra_api.config import Settings
from aevyra_api.credits.analysis import CreditAnalysisService
from aevyra_api.credits.ledger import append_credit, lock_wallet
from aevyra_api.credits.models import AccountSession, CreditTransaction, User, Wallet
from aevyra_api.owner import provision
from aevyra_api.preferences.models import (
    PreferenceDataset,
    PreferenceImage,
    PreferenceProject,
    PreferenceRating,
)
from aevyra_api.preferences.training_models import CustomModel
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess, ResearchJob
from aevyra_contracts.owner import BatchCreateCommand, CreditGrantCommand
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.mock import MockScoringEngine
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from test_postgres_commercial import postgres_services

pytestmark = pytest.mark.integration
PASSWORD = "synthetic-concurrent-owner-password"


def test_concurrent_owner_bootstrap_free_usage_grants_and_audit():
    with postgres_services() as (sessions, *_):

        def bootstrap(_):
            try:
                return provision(sessions, PASSWORD)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(bootstrap, range(4))).count("owner_god") == 1
        settings = Settings(api_environment="test", research_mode=True, _env_file=None)
        account = AccountService(sessions, settings)
        owner, token = account.login("owner_god", PASSWORD)
        ordinary, _ = account.register("ordinary-concurrent", PASSWORD)
        calls = []

        class Counting(MockScoringEngine):
            def predict(self, prepared):
                calls.append(1)
                return super().predict(prepared)

        scoring = CreditAnalysisService(sessions, EngineRegistry([Counting()]), production=False)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(
                pool.map(
                    lambda _: scoring.create(owner.id, "aevyra-test-analysis", "same-key"), range(6)
                )
            )
        assert len(set(results)) == 1 and len(calls) == 1
        body = CreditGrantCommand(
            idempotency_key=uuid4(), reason="Concurrent grant test", amount=27
        )
        admin = Administration(sessions, settings)

        def grant(_):
            return admin.mutate(
                owner.id,
                token,
                "credits.grant",
                ordinary.public_user_id,
                body,
                lambda s: admin.grant(s, owner.id, ordinary.public_user_id, body),
            )

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(grant, range(6)))
        assert all(result["balance"] == 27 for result in results)
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 1
            assert session.scalar(select(func.count()).select_from(FreeAnalysisGrant)) == 1
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(AdminAudit)
                    .where(AdminAudit.action == "credits.grant")
                )
                == 1
            )
        from aevyra_api.accounts import pepper
        from aevyra_api.commercial.state import DomainError

        batch = BatchCreateCommand(
            idempotency_key=uuid4(),
            reason="Concurrent export test",
            name="Concurrent",
            quantity=2,
            credits=5,
        )

        def create_batch(_):
            try:
                return admin.mutate(
                    owner.id,
                    token,
                    "batch.create",
                    "batch",
                    batch,
                    lambda s: admin.batch(s, pepper(settings), batch),
                    secrets_once=True,
                )
            except DomainError as exc:
                assert exc.status_code == 409
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            created = list(pool.map(create_batch, range(4)))
        assert sum(result is not None for result in created) == 1
        assert len(next(result for result in created if result)["codes"]) == 2
        queue = ResearchQueue(sessions, settings)
        for _ in range(4):
            queue.enqueue(owner.id, "mock", str(uuid4()))
        with ThreadPoolExecutor(max_workers=4) as pool:
            claimed = list(pool.map(lambda _: queue.claim(), range(4)))
        assert sum(lease is not None for lease in claimed) == 1
        for table in ("admin_audit", "free_analysis_grants"):
            for statement in (
                f"DELETE FROM {table}",
                f"TRUNCATE {table} CASCADE",
                f"UPDATE {table} SET created_at=created_at",
            ):
                with pytest.raises(DBAPIError), sessions.begin() as session:
                    session.execute(text(statement))
        # A second INSERT cannot create another Owner, even if bypassing application checks.
        with pytest.raises(DBAPIError), sessions.begin() as session:
            session.add(
                User(
                    public_user_id="usr_" + uuid4().hex,
                    login_identifier="owner_god",
                    role="owner",
                    password_hash=HASHER.hash(PASSWORD),
                )
            )


def test_incremental_migration_preserves_accounts_ledger_and_private_models(tmp_path):
    with postgres_services(revision="0006_custom_models") as (sessions, *_):
        user_id, public_id = uuid4(), "usr_" + uuid4().hex
        hashed = HASHER.hash(PASSWORD)
        old_token = "synthetic-old-session-token"
        artifact = tmp_path / "private-checkpoint.json"
        artifact.write_bytes(b'{"software_fixture":"private historical checkpoint bytes"}')
        with sessions.begin() as session:
            session.execute(
                text(
                    "INSERT INTO users(id,public_user_id,login_identifier,password_hash) "
                    "VALUES (:id,:public,:login,:hash)"
                ),
                {"id": user_id, "public": public_id, "login": "existing-user", "hash": hashed},
            )
            session.add(Wallet(user_id=user_id))
            session.add(
                AccountSession(
                    user_id=user_id,
                    token_digest=session_digest(old_token),
                    expires_at=now() + timedelta(days=1),
                )
            )
            session.add(
                ResearchAccess(user_id=user_id, enabled=True, reason="Existing operator grant")
            )
            project = PreferenceProject(user_id=user_id, name="Existing private project")
            session.add(project)
            session.flush()
            dataset = PreferenceDataset(
                project_id=project.id,
                name="Existing dataset",
                source="Synthetic",
                license="Software fixture",
                consent_version="adult-authorized-v1",
                source_url="",
                rating_min=1,
                rating_max=10,
                expires_at=now() + timedelta(days=30),
            )
            session.add(dataset)
            session.flush()
            image = PreferenceImage(
                dataset_id=dataset.id,
                artifact_id=uuid4(),
                thumbnail_id=uuid4(),
                content_hash="a" * 64,
                original_hash="d" * 64,
                consent_version="adult-authorized-v1",
                width=80,
                height=80,
                byte_size=100,
            )
            session.add(image)
            session.flush()
            session.add(PreferenceRating(image_id=image.id, score=7.5))
            job = ResearchJob(
                user_id=user_id,
                request_key="old-train",
                provider="custom",
                kind="TRAIN",
                status="COMPLETED",
            )
            session.add(job)
            session.flush()
            session.add(
                CustomModel(
                    user_id=user_id,
                    project_id=project.id,
                    dataset_id=dataset.id,
                    version=1,
                    training_job_id=job.id,
                    state="READY",
                    extractor="rgb-grid-texture-v1",
                    implementation="rating-ridge-v1",
                    configuration={},
                    snapshot={},
                    snapshot_sha256="b" * 64,
                    artifact_id=uuid4(),
                    artifact_sha256="c" * 64,
                    limitations=[],
                    expires_at=dataset.expires_at,
                )
            )
            append_credit(
                session,
                lock_wallet(session, user_id),
                amount=15,
                kind="PROMOTION",
                reference_type="test",
                reference_id="prior",
                key="prior",
            )
        with sessions() as session:
            bind = session.get_bind()
            tables = inspect(bind).get_table_names()
            before = {
                table: session.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
                for table in tables
                if table != "alembic_version"
            }
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with pytest.raises(RuntimeError, match="injected"), bind.begin() as connection:
            config.attributes["connection"] = connection

            def fail_table(*args, **kwargs):
                raise RuntimeError("injected migration failure")

            with patch("alembic.operations.Operations.create_table", new=fail_table):
                command.upgrade(config, "head")
        with bind.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0006_custom_models"
            )
            assert "role" not in {c["name"] for c in inspect(connection).get_columns("users")}
        with bind.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            command.check(config)
        with sessions() as session:
            for table, previous in before.items():
                current = [
                    dict(row)
                    for row in session.execute(text(f'SELECT * FROM "{table}"')).mappings()
                ]
                if table == "users":
                    assert all(row.pop("role") == "user" for row in current)
                assert current == previous, table
        assert (
            artifact.read_bytes() == b'{"software_fixture":"private historical checkpoint bytes"}'
        )
        account = AccountService(sessions, Settings(api_environment="test", _env_file=None))
        assert account.authenticate(old_token).public_user_id == public_id
        assert account.login("existing-user", PASSWORD)[0].role == "user"
        assert account.login("existing-user", PASSWORD)[0].password_hash == hashed
        provision(sessions, PASSWORD)
        # A new service/process session still sees the persisted Owner and ordinary data.
        assert (
            AccountService(sessions, account.config).login("owner_god", PASSWORD)[0].role == "owner"
        )


def test_interactive_terminal_bootstrap_confirmation_and_no_secret_output():
    import os
    import pty
    import secrets
    import select as io_select
    import subprocess
    import sys
    import time

    with postgres_services() as (sessions, *_):
        with sessions() as session:
            schema = session.scalar(text("SELECT current_schema()"))
            url = session.get_bind().url.update_query_dict({"options": f"-c search_path={schema}"})
        # DependencyChecks intentionally supplies its own connection options. A test-only
        # connect listener sets this random schema after connect instead of relying on
        # URL options that the real connection factory overrides.
        child = """
import os,re,runpy
from sqlalchemy import event,Engine
schema=os.environ['OWNER_TEST_SCHEMA']
assert re.fullmatch(r'aevyra_test_[a-f0-9]{32}',schema)
@event.listens_for(Engine,'connect')
def isolate(connection, record):
 old=connection.autocommit
 connection.autocommit=True
 connection.execute('SET search_path TO '+schema)
 connection.autocommit=old
runpy.run_module('aevyra_api.owner',run_name='__main__')
"""
        env = {
            **os.environ,
            "OWNER_TEST_SCHEMA": schema,
            "APP_ENV": "test",
            "CODESPACES": "true",
            "CODESPACE_NAME": "isolated-owner-cli-fixture",
            "DATABASE_URL": url.render_as_string(hide_password=False),
        }
        password = secrets.token_urlsafe(24)

        def interact(confirmation):
            master, slave = pty.openpty()
            process = subprocess.Popen(
                [sys.executable, "-c", child, "init"],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                env=env,
            )
            os.close(slave)
            output = b""
            sent = 0
            deadline = time.monotonic() + 15
            try:
                while time.monotonic() < deadline:
                    if io_select.select([master], [], [], 0.1)[0]:
                        try:
                            chunk = os.read(master, 8192)
                        except OSError:
                            break
                        if not chunk:
                            break
                        output += chunk
                    if sent == 0 and b"New Owner password" in output and output.endswith(b": "):
                        os.write(master, (password + "\n").encode())
                        sent = 1
                    elif sent == 1 and b"Confirm new Owner password: " in output:
                        os.write(master, (confirmation + "\n").encode())
                        sent = 2
                    if process.poll() is not None:
                        break
                result = process.wait(timeout=2)
                assert password.encode() not in output and confirmation.encode() not in output
                return result
            finally:
                os.close(master)
                if process.poll() is None:
                    process.kill()
                    process.wait()

        assert interact("synthetic-mismatch-confirmation") != 0
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 0
        assert interact(password) == 0
        assert interact(password) != 0
        account = AccountService(sessions, Settings(api_environment="test", _env_file=None))
        assert account.login("owner_god", password)[0].role == "owner"


def test_owner_thousand_image_capacity_keeps_training_and_storage_bounds(tmp_path):
    from aevyra_api.commercial.state import DomainError
    from aevyra_api.preferences.images import decode_image
    from aevyra_api.preferences.service import PreferenceService
    from aevyra_api.preferences.training import ModelService
    from aevyra_contracts.preferences import DatasetCreate, ImageUpload
    from aevyra_contracts.training import TrainRequest
    from test_preferences import encoded

    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test",
            research_mode=True,
            private_upload_root=tmp_path / "uploads",
            private_model_root=tmp_path / "models",
            _env_file=None,
        )
        provision(sessions, PASSWORD)
        owner, _ = AccountService(sessions, settings).login("owner_god", PASSWORD)
        data = PreferenceService(sessions, settings)
        project = data.create_project(owner.id, "Owner capacity")
        dataset = data.create_dataset(
            owner.id,
            DatasetCreate(
                project_id=project.id,
                name="Synthetic capacity",
                source="Generated colors",
                license="Software fixtures",
                adult_authorized_consent=True,
            ),
        )
        for i in range(1000):
            body = ImageUpload(
                content_base64=encoded((i % 256, i // 256, 50)), adult_authorized_consent=True
            )
            image = data.upload(owner.id, dataset.id, body, decode_image(body.content_base64))
            if i < 501:
                data.rate(owner.id, dataset.id, image.id, 1 + i % 10)
        overflow = ImageUpload(content_base64=encoded((5, 5, 5)), adult_authorized_consent=True)
        with pytest.raises(DomainError, match="quota reached"):
            data.upload(owner.id, dataset.id, overflow, decode_image(overflow.content_base64))
        with pytest.raises(DomainError, match="at most 500"):
            ModelService(sessions, settings).train(
                owner.id, TrainRequest(dataset_id=dataset.id, idempotency_key=uuid4())
            )
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(PreferenceImage)) == 1000
            assert session.scalar(select(func.count()).select_from(ResearchJob)) == 0
            assert session.scalar(select(func.sum(PreferenceImage.byte_size))) < 2048 * 1024 * 1024


def test_pr1_owner_upgrade_preserves_password_and_distinguishes_free_funding():
    from aevyra_api.commercial.state import DomainError

    with postgres_services(revision="0007_owner_role") as (sessions, *_):
        hashed = HASHER.hash(PASSWORD)
        with sessions.begin() as session:
            owner = User(
                public_user_id="usr_" + uuid4().hex,
                login_identifier="owner_god",
                role="owner",
                password_hash=hashed,
            )
            session.add(owner)
            session.flush()
            wallet = Wallet(user_id=owner.id)
            session.add(wallet)
            session.flush()
            free = Analysis(
                user_id=owner.id,
                credit_request_key="pr1-free",
                scoring_engine_slug="mock",
                status="FAILED",
            )
            paid = Analysis(
                user_id=owner.id,
                credit_request_key="prior-paid",
                scoring_engine_slug="mock",
                status="FAILED",
            )
            session.add_all([free, paid])
            session.flush()
            append_credit(
                session,
                wallet,
                amount=10,
                kind="PROMOTION",
                reference_type="test",
                reference_id="prior",
                key="prior",
            )
            append_credit(
                session,
                wallet,
                amount=-1,
                kind="ANALYSIS",
                reference_type="analysis",
                reference_id=str(paid.id),
                key=f"analysis:{paid.id}",
                metadata={"product_slug": "aevyra-test-analysis"},
            )
            owner_id, free_id, paid_id = owner.id, free.id, paid.id
        with sessions() as session:
            bind = session.get_bind()
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with bind.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            command.check(config)
        with sessions() as session:
            assert session.get(User, owner_id).password_hash == hashed
            assert session.get(FreeAnalysisGrant, free_id).policy == "owner-pr1-legacy"
            assert session.get(FreeAnalysisGrant, paid_id) is None
        service = CreditAnalysisService(
            sessions, EngineRegistry([MockScoringEngine()]), production=False
        )
        for _ in range(2):
            service.refund_failed(free_id)
            service.refund_failed(paid_id)
        assert service.create(owner_id, "aevyra-test-analysis", "pr1-free") == free_id
        with pytest.raises(DomainError, match="conflict"):
            service.create(owner_id, "different", "pr1-free")
        with sessions() as session:
            assert session.scalar(select(Wallet.cached_balance)) == 10
            assert session.scalar(select(func.count()).select_from(CreditTransaction)) == 3
        with pytest.raises(RuntimeError, match="history"), bind.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0007_owner_role")
