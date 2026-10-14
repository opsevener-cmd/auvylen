from uuid import UUID, uuid4

import pytest
from aevyra_api.preferences.training import ModelService
from aevyra_api.preferences.training_models import CustomModel, ImageEmbedding
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.worker import run_one
from sqlalchemy import func, select
from test_credits import credits as credits
from test_credits import user_id
from test_preferences import BASE, post, setup_dataset, upload


def populated(fixture):
    dataset = setup_dataset(fixture)
    for index in range(10):
        image = upload(
            fixture, dataset, (20 + index * 20, 40, 50), subject_group=f"subject-{index}"
        ).json()
        assert (
            post(
                fixture,
                f"/datasets/{dataset}/images/{image['id']}/rating",
                {"score": 1 + index * 0.8},
            ).status_code
            == 200
        )
    return dataset


def train_job(fixture, dataset, key=None, **config):
    response = post(
        fixture, "/train", {"dataset_id": dataset, "idempotency_key": str(key or uuid4()), **config}
    )
    assert response.status_code == 202, response.text
    return response.json()


def execute(fixture):
    assert run_one(ResearchQueue(fixture.sessions, fixture.client.app.state.settings))


def models(fixture):
    return fixture.client.get(BASE + "/models").json()


def test_training_checkpoint_unseen_prediction_and_retraining(credits):
    dataset = populated(credits)
    key = uuid4()
    first = train_job(credits, dataset, key)
    assert train_job(credits, dataset, key)["id"] == first["id"]
    execute(credits)
    model = models(credits)[0]
    assert model["state"] == "READY", credits.client.get("/api/v1/research/jobs").json()
    assert model["version"] == 1
    assert model["metrics"]["labeled_images"] == 10
    assert model["metrics"]["training_images"] + model["metrics"]["validation_images"] == 10
    assert set(model["metrics"]["training_image_ids"]).isdisjoint(
        model["metrics"]["validation_image_ids"]
    )
    assert "coefficients" not in model and "artifact_id" not in model
    with credits.sessions() as session:
        row = session.get(CustomModel, UUID(model["id"]))
        checkpoint = ModelService(credits.sessions, credits.client.app.state.settings).store.read(
            user_id(credits), row.artifact_id
        )
        assert b"coefficients" in checkpoint
        assert session.scalar(select(func.count()).select_from(ImageEmbedding)) == 10
    unseen = upload(credits, dataset, (125, 40, 50)).json()
    prediction = post(
        credits,
        "/predict",
        {
            "model_id": model["id"],
            "dataset_id": dataset,
            "image_id": unseen["id"],
            "idempotency_key": str(uuid4()),
        },
    )
    assert prediction.status_code == 202
    execute(credits)
    result = credits.client.get(f"/api/v1/research/jobs/{prediction.json()['id']}").json()
    assert result["status"] == "COMPLETED", result
    assert result["result"]["synthetic"] is False
    assert result["result"]["seen_in_training_snapshot"] is False
    assert 1 <= result["result"]["display_score"] <= 10
    assert result["result"]["model_version"] == 1
    assert result["progress"] == 100
    assert (
        post(
            credits, f"/datasets/{dataset}/images/{unseen['id']}/rating", {"score": 5.5}
        ).status_code
        == 200
    )
    train_job(credits, dataset)
    execute(credits)
    assert [m["version"] for m in models(credits)] == [2, 1]
    assert models(credits)[0]["metrics"]["labeled_images"] == 11
    with credits.sessions() as session:
        assert (
            ModelService(credits.sessions, credits.client.app.state.settings).store.read(
                user_id(credits), row.artifact_id
            )
            == checkpoint
        )
        assert session.scalar(select(func.count()).select_from(ImageEmbedding)) == 11
    assert credits.client.get("/api/v1/account").json()["wallet"] == {
        "balance": 0,
        "transactions": [],
    }


def test_insufficient_training_and_archive_delete_source_invalidation(credits):
    dataset = setup_dataset(credits)
    assert (
        post(
            credits, "/train", {"dataset_id": dataset, "idempotency_key": str(uuid4())}
        ).status_code
        == 422
    )
    # Complete a new dataset in the same authorized account.
    for i in range(10):
        image = upload(credits, dataset, (20 + i * 20, 40, 50)).json()
        post(credits, f"/datasets/{dataset}/images/{image['id']}/rating", {"score": 1 + i * 0.8})
    train_job(credits, dataset)
    execute(credits)
    model = models(credits)[0]
    unseen = upload(credits, dataset, "blue").json()
    assert (
        post(credits, f"/models/{model['id']}/edit", {"archived": True}).json()["state"]
        == "ARCHIVED"
    )
    assert (
        post(
            credits,
            "/predict",
            {
                "dataset_id": dataset,
                "image_id": unseen["id"],
                "model_id": model["id"],
                "idempotency_key": str(uuid4()),
            },
        ).status_code
        == 409
    )
    assert (
        post(credits, f"/models/{model['id']}/edit", {"archived": False}).json()["state"] == "READY"
    )
    source = models(credits)[0]["metrics"]["training_image_ids"][0]
    post(credits, f"/datasets/{dataset}/images/{source}/delete", {})
    assert (
        post(
            credits,
            "/predict",
            {
                "dataset_id": dataset,
                "image_id": unseen["id"],
                "model_id": model["id"],
                "idempotency_key": str(uuid4()),
            },
        ).status_code
        == 409
    )
    data = ModelService(credits.sessions, credits.client.app.state.settings)
    data.purge()
    assert models(credits)[0]["state"] == "DELETED"
    assert list(data.store.root.glob("*/*")) == []


def test_snapshot_is_immutable_and_cancelled_training_never_publishes(credits):
    from unittest.mock import patch

    from aevyra_api.preferences.execution import CustomExecution
    from aevyra_api.preferences.models import PreferenceRating

    dataset = populated(credits)
    job = train_job(credits, dataset)
    original = models(credits)[0]
    with credits.sessions.begin() as session:
        for rating in session.scalars(select(PreferenceRating)):
            rating.score = 10 - rating.score
    execute(credits)
    with credits.sessions() as session:
        snapshot = session.get(CustomModel, UUID(original["id"])).snapshot
        assert any(example["score"] == 1 for example in snapshot["examples"])
    job = train_job(credits, dataset)
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    extract_original = CustomExecution.embedding

    def cancel_on_embedding(execution, id):
        result = extract_original(execution, id)
        queue.cancel(user_id(credits), UUID(job["id"]))
        return result

    with patch.object(CustomExecution, "embedding", cancel_on_embedding):
        execute(credits)
    assert models(credits)[0]["state"] == "FAILED"
    with credits.sessions() as session:
        latest = session.get(CustomModel, UUID(models(credits)[0]["id"]))
        assert latest.artifact_id is None
    data = ModelService(credits.sessions, credits.client.app.state.settings)
    assert len(list(data.store.root.glob("*/*"))) == 1


def test_stale_worker_cannot_publish_checkpoint_and_retry_keeps_version(credits):
    from datetime import timedelta
    from unittest.mock import patch

    from aevyra_api.commercial.models import now
    from aevyra_api.research.models import ResearchJob
    from aevyra_api.research.storage import PrivateArtifactStore

    dataset = populated(credits)
    job = train_job(credits, dataset)
    queue = ResearchQueue(credits.sessions, credits.client.app.state.settings)
    original_put = PrivateArtifactStore.put
    newer = None

    def steal_lease(store, owner, payload):
        nonlocal newer
        result = original_put(store, owner, payload)
        with credits.sessions.begin() as session:
            session.get(ResearchJob, UUID(job["id"])).lease_until = now() - timedelta(seconds=1)
        newer = queue.claim()
        assert newer is not None
        return result

    with patch.object(PrivateArtifactStore, "put", steal_lease):
        execute(credits)
    data = ModelService(credits.sessions, credits.client.app.state.settings)
    assert models(credits)[0]["state"] == "TRAINING"
    assert list(data.store.root.glob("*/*")) == []
    with credits.sessions.begin() as session:
        session.get(ResearchJob, newer.id).lease_until = now() - timedelta(seconds=1)
    execute(credits)
    assert models(credits)[0]["state"] == "READY"
    assert models(credits)[0]["version"] == 1
    assert len(models(credits)) == 1


def test_checkpoint_corruption_and_cross_owner_access_fail_without_predictions(credits):
    from aevyra_api.credits.models import User
    from aevyra_api.research.models import ResearchAccess
    from test_credits import register

    dataset = populated(credits)
    train_job(credits, dataset)
    execute(credits)
    model = models(credits)[0]
    image = upload(credits, dataset, "blue").json()
    body = {
        "dataset_id": dataset,
        "image_id": image["id"],
        "model_id": model["id"],
        "idempotency_key": str(uuid4()),
    }
    with credits.sessions() as session:
        row = session.get(CustomModel, UUID(model["id"]))
        store = ModelService(credits.sessions, credits.client.app.state.settings).store
        store._path(user_id(credits), row.artifact_id).write_bytes(b"corrupt checkpoint")
    queued = post(credits, "/predict", body).json()
    execute(credits)
    result = credits.client.get(f"/api/v1/research/jobs/{queued['id']}").json()
    assert result["status"] == "FAILED" and result["result"] is None
    owner = user_id(credits)
    register(credits.client, "another-model-owner")
    with credits.sessions.begin() as session:
        other = session.scalar(select(User).where(User.id != owner))
        session.add(ResearchAccess(user_id=other.id, enabled=True, reason="test"))
    assert post(credits, "/predict", body).status_code == 404
    assert post(credits, f"/models/{model['id']}/delete", {}).status_code == 404
    assert models(credits) == []


def test_deleting_model_preserves_annotations_and_erases_checkpoint(credits):
    from aevyra_api.preferences.models import PreferenceRating

    dataset = populated(credits)
    train_job(credits, dataset)
    execute(credits)
    model = models(credits)[0]
    assert post(credits, f"/models/{model['id']}/delete", {}).status_code == 200
    data = ModelService(credits.sessions, credits.client.app.state.settings)
    data.purge()
    assert list(data.store.root.glob("*/*")) == []
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(PreferenceRating)) == 10
        deleted = session.get(CustomModel, UUID(model["id"]))
        assert deleted.snapshot == {}
        assert "training_image_ids" not in deleted.metrics
        assert "validation_image_ids" not in deleted.metrics


def test_extractor_availability_ownership_and_no_missing_weight_fallback(credits):
    from aevyra_inference.extractors import MOBILENET

    dataset = populated(credits)
    options = credits.client.get(BASE + "/extractors")
    assert options.status_code == 200
    assert options.json()[0]["available"] is True
    assert options.json()[1]["available"] is False
    assert options.json()[1]["manifest"]["weight_license"] == "Apache-2.0"
    rejected = post(
        credits,
        "/train",
        {"dataset_id": dataset, "idempotency_key": str(uuid4()), "extractor": MOBILENET},
    )
    assert rejected.status_code == 503
    assert models(credits) == []
    rejected = post(
        credits,
        "/train",
        {"dataset_id": dataset, "idempotency_key": str(uuid4()), "extractor": "unknown"},
    )
    assert rejected.status_code == 422
    credits.client.cookies.clear()
    assert credits.client.get(BASE + "/extractors").status_code == 401


@pytest.mark.pretrained
def test_pretrained_job_matched_comparison_cached_retraining_and_old_checkpoint(
    credits, pretrained_root
):
    import shutil

    from aevyra_inference.extractors import MOBILENET, WEIGHT_FILE

    dataset = populated(credits)
    train_job(credits, dataset)
    execute(credits)
    legacy = models(credits)[0]
    settings = credits.client.app.state.settings
    target = settings.private_model_root / "pretrained"
    target.mkdir(parents=True)
    shutil.copyfile(pretrained_root / WEIGHT_FILE, target / WEIGHT_FILE)
    train_job(credits, dataset, extractor=MOBILENET)
    execute(credits)
    first = models(credits)[0]
    assert first["state"] == "READY", credits.client.get("/api/v1/research/jobs").json()
    assert first["version"] == 2 and first["extractor"] == MOBILENET
    metrics = first["metrics"]
    assert metrics["training_image_ids"] == legacy["metrics"]["training_image_ids"]
    assert metrics["validation_image_ids"] == legacy["metrics"]["validation_image_ids"]
    assert metrics["handcrafted_baseline_mae"] == legacy["metrics"]["validation_mae"]
    assert metrics["handcrafted_baseline_rmse"] == legacy["metrics"]["validation_rmse"]
    assert metrics["mean_baseline_mae"] == legacy["metrics"]["mean_baseline_mae"]
    assert metrics["embedding_cache_hits"] == 10 and metrics["embedding_cache_misses"] == 10
    train_job(credits, dataset, extractor=MOBILENET)
    execute(credits)
    assert models(credits)[0]["metrics"]["embedding_cache_hits"] == 20
    assert models(credits)[0]["metrics"]["embedding_cache_misses"] == 0
    image = upload(credits, dataset, (125, 40, 50)).json()

    def predict(model):
        job = post(
            credits,
            "/predict",
            {
                "model_id": model["id"],
                "dataset_id": dataset,
                "image_id": image["id"],
                "idempotency_key": str(uuid4()),
            },
        ).json()
        execute(credits)
        return credits.client.get(f"/api/v1/research/jobs/{job['id']}").json()

    predicted = predict(first)
    assert predicted["status"] == "COMPLETED" and predicted["result"]["synthetic"] is False
    assert predicted["result"]["seen_in_training_snapshot"] is False
    assert predicted["result"]["raw_score"] == predict(first)["result"]["raw_score"]
    assert predict(legacy)["status"] == "COMPLETED"
    (target / WEIGHT_FILE).write_bytes(b"corrupted")
    assert predict(first)["status"] == "FAILED"
    assert predict(legacy)["status"] == "COMPLETED"  # Legacy unaffected by pretrained removal.
    with credits.sessions() as session:
        assert session.scalar(select(func.count()).select_from(ImageEmbedding)) == 22
    assert credits.client.get("/api/v1/account").json()["wallet"]["balance"] == 0
