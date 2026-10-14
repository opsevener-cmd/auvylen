"""Custom jobs run only in the leased worker; checkpoint publication is fenced."""

import hashlib
import logging
import math
import time
from uuid import UUID

from aevyra_contracts.training import PredictRequest, TrainRequest
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.extractors import (
    BATCH_SIZE,
    FeatureExtractor,
    create_extractor,
    dimension,
    manifest,
)
from aevyra_inference.preference import (
    DIMENSION,
    EXTRACTOR,
    PersonalRatingEngine,
    RatingCheckpoint,
    checkpoint_adapter,
    extract,
    rating_metadata,
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
        self.cache_hits = 0
        self.cache_misses = 0

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
            if (
                cached
                and cached.source_sha256 == sha256
                and len(cached.features) == DIMENSION
                and all(math.isfinite(v) for v in cached.features)
            ):
                self.cache_hits += 1
                return cached.features
            self.cache_misses += 1
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

    def batch_embeddings(self, ids: list[UUID], extractor: FeatureExtractor) -> list[list[float]]:
        if not 1 <= len(ids) <= BATCH_SIZE or len(ids) != len(set(ids)):
            raise ValueError("Embedding batch limit")
        self.heartbeat.check()
        with self.queue.sessions.begin() as session:
            self.service.data.access(session, self.lease.user_id)
            candidates = list(
                session.scalars(select(PreferenceImage).where(PreferenceImage.id.in_(ids)))
            )
            if len(candidates) != len(ids):
                raise DomainError("Source image removed", 409)
            # Follow the same dataset-before-image lock order as retention/deletion.
            for dataset_id in sorted({image.dataset_id for image in candidates}):
                self.service.data.dataset(session, self.lease.user_id, dataset_id)
            images = list(
                session.scalars(
                    select(PreferenceImage)
                    .where(PreferenceImage.id.in_(ids), PreferenceImage.deleted_at.is_(None))
                    .order_by(PreferenceImage.id)
                    .with_for_update()
                )
            )
            if len(images) != len(ids):
                raise DomainError("Source image removed", 409)
            found = {
                row.image_id: row
                for row in session.scalars(
                    select(ImageEmbedding).where(
                        ImageEmbedding.image_id.in_(ids),
                        ImageEmbedding.extractor == extractor.identifier,
                    )
                )
            }
            values: dict[UUID, list[float]] = {}
            missing = []
            for image in images:
                payload = self.service.data.store.read(self.lease.user_id, image.artifact_id)
                sha = hashlib.sha256(payload).hexdigest()
                cached = found.get(image.id)
                if (
                    cached
                    and cached.source_sha256 == sha
                    and len(cached.features) == dimension(extractor.identifier)
                    and all(math.isfinite(v) for v in cached.features)
                ):
                    values[image.id] = cached.features
                    self.cache_hits += 1
                else:
                    missing.append((image.id, sha, payload))
            if missing:
                vectors = extractor.extract_batch([item[2] for item in missing])
                self.heartbeat.check()
                for (id, sha, _), vector in zip(missing, vectors, strict=True):
                    cached = found.get(id)
                    if cached:
                        cached.features, cached.source_sha256 = vector, sha
                    else:
                        session.add(
                            ImageEmbedding(
                                image_id=id,
                                extractor=extractor.identifier,
                                source_sha256=sha,
                                features=vector,
                            )
                        )
                    values[id] = vector
                    self.cache_misses += 1
            return [values[id] for id in ids]

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
            rating_metadata(str(model.version), model.snapshot_sha256, model.extractor),
            production=self.queue.settings.api_environment == "production",
            purpose="research",
        )
        if request.extractor != model.extractor:
            raise ValueError("Saved extractor configuration mismatch")
        self.check(1, "Extracting visual features")
        features: list[list[float]] = []
        handcrafted: list[list[float]] = []
        if model.extractor == EXTRACTOR:
            for index, example in enumerate(snapshot.examples):
                self.check(
                    1 + int(70 * index / len(snapshot.examples)), "Extracting visual features"
                )
                features.append(self.embedding(example.image_id))
        else:
            extractor = create_extractor(
                model.extractor, self.queue.settings.private_model_root / "pretrained"
            )
            for index in range(0, len(snapshot.examples), BATCH_SIZE):
                self.check(
                    1 + int(70 * index / len(snapshot.examples)),
                    "Extracting pretrained batches and baseline",
                )
                examples = snapshot.examples[index : index + BATCH_SIZE]
                features.extend(self.batch_embeddings([e.image_id for e in examples], extractor))
                handcrafted.extend(self.embedding(e.image_id) for e in examples)
        extraction_seconds = time.monotonic() - started
        self.check(75, "Fitting rating regression")

        def fit(
            vectors: list[list[float]], identifier: str
        ) -> tuple[RatingCheckpoint, dict[str, float | int], list[int], list[int]]:
            return train(
                vectors,
                [e.score for e in snapshot.examples],
                [e.group for e in snapshot.examples],
                alpha=request.alpha,
                seed=request.seed,
                validation_fraction=request.validation_fraction,
                rating_min=snapshot.rating_min,
                rating_max=snapshot.rating_max,
                snapshot_sha256=model.snapshot_sha256,
                extractor=identifier,
                check=lambda: self.check(75, "Fitting and validating grouped split"),
            )

        checkpoint, measured, training, validation = fit(features, model.extractor)
        if handcrafted:
            _, baseline, baseline_train, baseline_validation = fit(handcrafted, EXTRACTOR)
            if (training, validation) != (baseline_train, baseline_validation):
                raise ValueError("Comparison split mismatch")
        else:
            baseline = measured
        metrics: dict[str, JsonValue] = dict(measured)
        metrics.update(
            {
                "representation": manifest(model.extractor),
                "handcrafted_baseline_mae": baseline["validation_mae"],
                "handcrafted_baseline_rmse": baseline["validation_rmse"],
                "comparison_protocol": (
                    "identical snapshot, groups, seed, alpha and held-out images; "
                    "training-only normalization"
                ),
                "extraction_duration_seconds": extraction_seconds,
                "fit_and_validation_seconds": time.monotonic() - started - extraction_seconds,
                "embedding_cache_hits": self.cache_hits,
                "embedding_cache_misses": self.cache_misses,
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
                "extractor": model.extractor,
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
            checkpoint = checkpoint_adapter.validate_json(raw)
            if (
                checkpoint.snapshot_sha256 != model.snapshot_sha256
                or checkpoint.extractor != model.extractor
            ):
                raise ValueError("Checkpoint snapshot mismatch")
            payload = self.service.data.store.read(self.lease.user_id, image.artifact_id)
            snapshot = TrainingSnapshot.model_validate(model.snapshot)
            seen = any(e.content_hash == image.content_hash for e in snapshot.examples)
        self.check(50, "Predicting with saved model")
        root = self.queue.settings.private_model_root / "pretrained"
        EngineRegistry.check_policy(
            rating_metadata(str(model.version), model.snapshot_sha256, model.extractor),
            production=self.queue.settings.api_environment == "production",
            purpose="research",
        )
        # Verify installed pretrained weights even when the image embedding is cached.
        if model.extractor != EXTRACTOR:
            features = self.batch_embeddings([image.id], create_extractor(model.extractor, root))[0]
        else:
            features = self.embedding(image.id)
        score = EngineRegistry(
            [PersonalRatingEngine(checkpoint, str(model.version), root, features)]
        ).score(
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
                "extractor": model.extractor,
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
