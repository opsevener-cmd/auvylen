"""Custom jobs run only in the leased worker; checkpoint publication is fenced."""

import hashlib
import logging
import time
from uuid import UUID

from aevyra_contracts.training import PredictRequest, TrainRequest
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.preference import (
    DIMENSION,
    EXTRACTOR,
    PersonalRatingEngine,
    RidgeCheckpoint,
    baseline_metadata,
    extract,
    train,
)
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.preferences.models import PreferenceImage
from aevyra_api.preferences.training import ModelService, TrainingSnapshot, digest
from aevyra_api.preferences.training_models import CustomModel, ImageEmbedding
from aevyra_api.research.jobs import JobLease, ResearchQueue
from aevyra_api.research.lease import LeaseHeartbeat
from aevyra_api.research.models import ResearchJob

logger = logging.getLogger("aevyra.worker")


class CustomExecution:
    def __init__(self, queue: ResearchQueue, lease: JobLease, heartbeat: LeaseHeartbeat):
        self.queue, self.lease, self.heartbeat = queue, lease, heartbeat
        self.service = ModelService(queue.sessions, queue.settings)

    def check(self, percent: int, phase: str) -> None:
        self.heartbeat.check()
        if not self.queue.progress(self.lease, percent, phase):
            raise RuntimeError("Custom job cancelled, expired or revoked")
        logger.info("custom_job_progress", extra={"analysis_id": str(self.lease.id)})

    def embedding(self, id: UUID) -> list[float]:
        self.heartbeat.check()
        with self.queue.sessions.begin() as session:
            candidate = session.get(PreferenceImage, id)
            if candidate is None:
                raise DomainError("Source image removed", 409)
            self.service.data.dataset(session, self.lease.user_id, candidate.dataset_id)
            image = session.scalar(
                select(PreferenceImage)
                .where(PreferenceImage.id == id, PreferenceImage.deleted_at.is_(None))
                .with_for_update()
            )
            if image is None:
                raise DomainError("Source image removed", 409)
            self.service.data.dataset(session, self.lease.user_id, image.dataset_id)
            payload = self.service.data.store.read(self.lease.user_id, image.artifact_id)
            sha256 = hashlib.sha256(payload).hexdigest()
            cached = session.scalar(
                select(ImageEmbedding).where(
                    ImageEmbedding.image_id == id, ImageEmbedding.extractor == EXTRACTOR
                )
            )
            if cached and cached.source_sha256 == sha256 and len(cached.features) == DIMENSION:
                return cached.features
            vector = extract(payload)
            if cached:
                cached.features, cached.source_sha256 = vector, sha256
            else:
                session.add(
                    ImageEmbedding(
                        image_id=id, extractor=EXTRACTOR, source_sha256=sha256, features=vector
                    )
                )
            return vector

    def train(self) -> bool:
        started = time.monotonic()
        artifact: UUID | None = None
        with self.queue.sessions() as session:
            model = session.scalar(
                select(CustomModel).where(
                    CustomModel.training_job_id == self.lease.id,
                    CustomModel.user_id == self.lease.user_id,
                )
            )
            if (
                model is None
                or model.state != "TRAINING"
                or not self.service.source_valid(session, model)
            ):
                raise DomainError("Training model or source data unavailable", 409)
            snapshot = TrainingSnapshot.model_validate(model.snapshot)
            if digest(snapshot) != model.snapshot_sha256:
                raise ValueError("Training snapshot integrity failure")
            request = TrainRequest.model_validate(
                {
                    **model.configuration,
                    "dataset_id": model.dataset_id,
                    "idempotency_key": self.lease.id,
                }
            )
        EngineRegistry.check_policy(
            baseline_metadata(str(model.version), model.snapshot_sha256),
            production=self.queue.settings.api_environment == "production",
            purpose="research",
        )
        self.check(1, "Extracting visual features")
        features: list[list[float]] = []
        for index, example in enumerate(snapshot.examples):
            self.check(1 + int(70 * index / len(snapshot.examples)), "Extracting visual features")
            features.append(self.embedding(example.image_id))
        self.check(75, "Fitting rating regression")
        checkpoint, measured, training, validation = train(
            features,
            [e.score for e in snapshot.examples],
            [e.group for e in snapshot.examples],
            alpha=request.alpha,
            seed=request.seed,
            validation_fraction=request.validation_fraction,
            rating_min=snapshot.rating_min,
            rating_max=snapshot.rating_max,
            snapshot_sha256=model.snapshot_sha256,
            check=lambda: self.check(75, "Fitting and validating grouped split"),
        )
        metrics: dict[str, JsonValue] = dict(measured)
        metrics.update(
            {
                "known_subject_groups": len(
                    {e.group for e in snapshot.examples if e.subject_known}
                ),
                "unknown_subject_images": sum(not e.subject_known for e in snapshot.examples),
                "training_duration_seconds": time.monotonic() - started,
                "training_image_ids": [str(snapshot.examples[i].image_id) for i in training],
                "validation_image_ids": [str(snapshot.examples[i].image_id) for i in validation],
            }
        )
        # IDs remain private metadata. Coefficients never leave the private model store.
        self.check(95, "Saving versioned checkpoint")
        try:
            artifact, sha256 = self.service.store.put(
                self.lease.user_id, checkpoint.model_dump_json().encode()
            )

            def publish(session: Session) -> None:
                current = session.get(CustomModel, model.id)
                if (
                    current is None
                    or current.state != "TRAINING"
                    or not self.service.source_valid(session, current)
                ):
                    raise DomainError("Training publication no longer authorized", 409)
                current.artifact_id, current.artifact_sha256 = artifact, sha256
                current.metrics, current.state, current.completed_at = metrics, "READY", now()

            result: dict[str, JsonValue] = {
                "model_id": str(model.id),
                "model_version": model.version,
                "provider": "custom",
                "prediction_type": "subjective_rating",
                "metrics": metrics,
                "extractor": EXTRACTOR,
                "synthetic": False,
            }
            saved = self.queue.finish(self.lease, result, publish)
            if not saved:
                self.service.store.delete(self.lease.user_id, artifact)
            return saved
        except Exception:
            if artifact:
                self.service.store.delete(self.lease.user_id, artifact)
            raise

    def predict(self) -> bool:
        started = time.monotonic()
        with self.queue.sessions() as session:
            job = session.get(ResearchJob, self.lease.id)
            if job is None or job.payload is None:
                raise DomainError("Prediction request unavailable", 409)
            body = PredictRequest.model_validate(
                {key: value for key, value in job.payload.items() if key != "operation"}
                | {"idempotency_key": self.lease.id}
            )
            model = self.service.owned(session, self.lease.user_id, body.model_id, ready=True)
            self.service.data.dataset(session, self.lease.user_id, body.dataset_id)
            image = self.service.data.image(session, body.dataset_id, body.image_id)
            if model.artifact_id is None:
                raise DomainError("Checkpoint unavailable", 409)
            raw = self.service.store.read(self.lease.user_id, model.artifact_id)
            if hashlib.sha256(raw).hexdigest() != model.artifact_sha256:
                raise ValueError("Checkpoint integrity failure")
            checkpoint = RidgeCheckpoint.model_validate_json(raw)
            if checkpoint.snapshot_sha256 != model.snapshot_sha256:
                raise ValueError("Checkpoint snapshot mismatch")
            payload = self.service.data.store.read(self.lease.user_id, image.artifact_id)
            snapshot = TrainingSnapshot.model_validate(model.snapshot)
            seen = any(e.content_hash == image.content_hash for e in snapshot.examples)
        self.check(50, "Predicting with saved model")
        score = EngineRegistry([PersonalRatingEngine(checkpoint, str(model.version))]).score(
            "custom",
            payload,
            production=self.queue.settings.api_environment == "production",
            purpose="research",
        )
        self.check(95, "Saving prediction")
        result: dict[str, JsonValue] = score.model_dump(mode="json")
        result.update(
            {
                "model_id": str(model.id),
                "model_version": model.version,
                "provider": "custom",
                "input_image_id": str(image.id),
                "prediction_type": "subjective_rating",
                "score_min": checkpoint.rating_min,
                "score_max": checkpoint.rating_max,
                "seen_in_training_snapshot": seen,
                "processing_duration_ms": (time.monotonic() - started) * 1000,
            }
        )

        def verify(session: Session) -> None:
            self.service.owned(session, self.lease.user_id, model.id, ready=True)
            self.service.data.dataset(session, self.lease.user_id, body.dataset_id)
            self.service.data.image(session, body.dataset_id, body.image_id)

        return self.queue.finish(self.lease, result, verify)

    def fail(self) -> None:
        # Mark failure only after the matching fenced queue completion/cancellation exists.
        with self.queue.sessions.begin() as session:
            job = session.get(ResearchJob, self.lease.id)
            if job and job.status == "FAILED":
                model = session.scalar(
                    select(CustomModel).where(CustomModel.training_job_id == job.id)
                )
                if model and model.state == "TRAINING":
                    model.state, model.completed_at = "FAILED", now()
