"""500-image quota boundary on real PostgreSQL, private storage and durable jobs."""

import json
import os
import shutil
import time
from pathlib import Path
from uuid import uuid4

import pytest
from aevyra_api.accounts import AccountService
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.preferences.images import decode_image
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.preferences.training import ModelService
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchAccess
from aevyra_api.research.worker import run_one
from aevyra_contracts.preferences import DatasetCreate, ImageUpload
from aevyra_contracts.training import TrainRequest
from aevyra_inference.extractors import BASELINE, MOBILENET, WEIGHT_FILE
from test_postgres_commercial import postgres_services
from test_preferences import encoded


@pytest.mark.integration
@pytest.mark.parametrize(
    "extractor", [BASELINE, pytest.param(MOBILENET, marks=pytest.mark.pretrained)]
)
def test_five_hundred_images_actual_worker_quota_cache_and_cleanup(tmp_path, request, extractor):
    with postgres_services() as (sessions, *_):
        settings = Settings(
            api_environment="test",
            research_mode=True,
            private_upload_root=tmp_path / "uploads",
            private_model_root=tmp_path / "models",
            _env_file=None,
        )
        if extractor == MOBILENET:
            source = request.getfixturevalue("pretrained_root")
            target = settings.private_model_root / "pretrained"
            target.mkdir(parents=True)
            shutil.copyfile(source / WEIGHT_FILE, target / WEIGHT_FILE)
        user, _ = AccountService(sessions, settings).register(
            "capacity-owner", "test-only-capacity-password"
        )
        with sessions.begin() as session:
            session.add(
                ResearchAccess(user_id=user.id, enabled=True, reason="synthetic capacity test")
            )
        data = PreferenceService(sessions, settings)
        project = data.create_project(user.id, "Capacity")
        dataset = data.create_dataset(
            user.id,
            DatasetCreate(
                project_id=project.id,
                name="Synthetic only",
                source="Generated colors",
                license="Generated fixture",
                adult_authorized_consent=True,
            ),
        )
        before = time.perf_counter()
        for i in range(500):
            body = ImageUpload(
                content_base64=encoded((i % 256, i // 256, 50)),
                adult_authorized_consent=True,
                subject_group=str(i // 2),
            )
            image = data.upload(user.id, dataset.id, body, decode_image(body.content_base64))
            data.rate(user.id, dataset.id, image.id, 1 + i % 10)
        ingestion = time.perf_counter() - before
        overflow = ImageUpload(content_base64=encoded((5, 5, 5)), adult_authorized_consent=True)
        with pytest.raises(DomainError, match="quota reached"):
            data.upload(user.id, dataset.id, overflow, decode_image(overflow.content_base64))
        service = ModelService(sessions, settings)
        service.train(
            user.id,
            TrainRequest(dataset_id=dataset.id, idempotency_key=uuid4(), extractor=extractor),
        )
        before = time.perf_counter()
        assert run_one(ResearchQueue(sessions, settings))
        duration = time.perf_counter() - before
        first = service.list(user.id)[0]
        assert first.state == "READY"
        assert first.metrics["labeled_images"] == 500
        assert first.metrics["training_images"] == 400 and first.metrics["validation_images"] == 100
        service.train(
            user.id,
            TrainRequest(dataset_id=dataset.id, idempotency_key=uuid4(), extractor=extractor),
        )
        before = time.perf_counter()
        assert run_one(ResearchQueue(sessions, settings))
        cached = time.perf_counter() - before
        second = service.list(user.id)[0]
        assert second.state == "READY"
        assert second.metrics["embedding_cache_misses"] == 0
        assert second.metrics["embedding_cache_hits"] == (500 if extractor == BASELINE else 1000)
        assert second.metrics["validation_mae"] == first.metrics["validation_mae"]
        report = {
            "synthetic_only": True,
            "images": 500,
            "extractor": extractor,
            "ingestion_and_annotations_seconds": ingestion,
            "first_job_wall_seconds": duration,
            "cached_job_wall_seconds": cached,
            "cache_hits": second.metrics["embedding_cache_hits"],
            "private_upload_bytes": sum(
                p.stat().st_size for p in settings.private_upload_root.rglob("*") if p.is_file()
            ),
            "quota_501_rejected": True,
        }
        if directory := os.environ.get("AUVYLEN_BENCHMARK_REPORT"):
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            (target / f"worker-500-{extractor}.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
        data.delete(user.id, dataset.id)
        service.purge()
        # Retention batches are bounded; drain all synthetic data via normal cleanup.
        while data.purge():
            pass
        assert all(m.state == "DELETED" for m in service.list(user.id))
        assert list(data.store.root.glob("*/*")) == []
