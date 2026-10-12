from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from aevyra_api.accounts import AccountService
from aevyra_api.config import Settings
from aevyra_api.preferences.images import decode_image
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.preferences.training import ModelService
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess
from aevyra_api.research.worker import run_one
from aevyra_contracts.preferences import DatasetCreate, ImageUpload
from aevyra_contracts.training import TrainRequest
from test_postgres_commercial import postgres_services
from test_preferences import encoded

pytestmark = pytest.mark.integration


def test_postgres_concurrent_train_idempotency_and_durable_versions(tmp_path):
    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test",
            research_mode=True,
            private_upload_root=tmp_path / "uploads",
            private_model_root=tmp_path / "models",
            _env_file=None,
        )
        user, _ = AccountService(sessions, settings).register(
            "training-owner", "test-only-training-password"
        )
        with sessions.begin() as session:
            session.add(ResearchAccess(user_id=user.id, enabled=True, reason="test"))
        data = PreferenceService(sessions, settings)
        project = data.create_project(user.id, "Training")
        dataset = data.create_dataset(
            user.id,
            DatasetCreate(
                project_id=project.id,
                name="Synthetic",
                source="Generated colors",
                license="Generated fixture",
                adult_authorized_consent=True,
            ),
        )
        for i in range(10):
            upload = ImageUpload(
                content_base64=encoded((20 + i * 20, 40, 50)),
                adult_authorized_consent=True,
                subject_group=str(i),
            )
            image = data.upload(user.id, dataset.id, upload, decode_image(upload.content_base64))
            data.rate(user.id, dataset.id, image.id, 1 + i * 0.8)
        service = ModelService(sessions, settings)
        body = TrainRequest(dataset_id=dataset.id, idempotency_key=uuid4())
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(lambda _: service.train(user.id, body).id, range(6)))
        assert len(set(ids)) == 1
        assert len(service.list(user.id)) == 1
        assert run_one(ResearchQueue(sessions, settings))
        saved = ModelService(sessions, settings).list(user.id)[0]
        assert saved.state == "READY"
        assert saved.metrics["training_images"] + saved.metrics["validation_images"] == 10
        service.train(user.id, TrainRequest(dataset_id=dataset.id, idempotency_key=uuid4()))
        assert run_one(ResearchQueue(sessions, settings))
        assert [m.version for m in service.list(user.id)] == [2, 1]
        # Source expiry/delete and SQL FK cascades coexist with all previous migrations.
        data.delete(user.id, dataset.id)
        service.purge()
        assert data.purge() == 10
        assert all(m.state == "DELETED" for m in service.list(user.id))
