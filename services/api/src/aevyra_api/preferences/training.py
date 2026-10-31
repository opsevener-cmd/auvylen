"""Owned immutable rating snapshots, version allocation and private model lifecycle."""

import hashlib
from datetime import timedelta
from typing import Literal, cast
from uuid import UUID

from aevyra_contracts.preferences import TrainingReadiness
from aevyra_contracts.research import ResearchJobView
from aevyra_contracts.training import ExtractorView, ModelView, PredictRequest, TrainRequest
from aevyra_inference.extractors import MOBILENET, availability, manifest
from aevyra_inference.preference import EXTRACTOR, IMPLEMENTATION, split_groups
from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.entitlements import research_limits
from aevyra_api.preferences.models import PreferenceDataset as Dataset
from aevyra_api.preferences.models import PreferenceImage as Image
from aevyra_api.preferences.models import PreferenceRating as Rating
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.preferences.training_models import CustomModel
from aevyra_api.research.jobs import ResearchQueue
from aevyra_api.research.models import ResearchJob
from aevyra_api.research.storage import PrivateArtifactStore

REQUIRED_RATINGS = 8
REQUIRED_GROUPS = 5
ReadinessReason = Literal[
    "archived",
    "too_few_ratings",
    "too_few_groups",
    "insufficient_split",
    "no_score_variation",
    "too_many_ratings",
]


class Example(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    image_id: UUID
    artifact_id: UUID
    content_hash: str
    score: float
    group: str
    subject_known: bool


class TrainingSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dataset_id: UUID
    consent_version: str
    rating_min: int
    rating_max: int
    examples: list[Example]


def digest(snapshot: TrainingSnapshot) -> str:
    return hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()


class ModelService:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions, self.settings = sessions, settings
        self.data = PreferenceService(sessions, settings)
        self.queue = ResearchQueue(sessions, settings)
        self.store = PrivateArtifactStore(settings.private_model_root / "custom")

    def extractors(self, user: UUID) -> list[ExtractorView]:
        with self.sessions() as session:
            self.data.access(session, user)
        result = []
        for identifier in (EXTRACTOR, MOBILENET):
            available, reason = availability(
                identifier, self.settings.private_model_root / "pretrained"
            )
            result.append(
                ExtractorView(
                    id=identifier, available=available, reason=reason, manifest=manifest(identifier)
                )
            )
        return result

    def existing(
        self, session: Session, user: UUID, key: UUID, payload: dict[str, JsonValue]
    ) -> ResearchJob | None:
        job = session.scalar(
            select(ResearchJob).where(
                ResearchJob.user_id == user, ResearchJob.request_key == str(key)
            )
        )
        if job and (job.provider != "custom" or job.payload != payload):
            raise DomainError("Research request key conflict", 409)
        return job

    def source_valid(self, session: Session, model: CustomModel) -> bool:
        if model.dataset_id is None or not model.snapshot:
            return False
        dataset = session.scalar(
            select(Dataset).where(
                Dataset.id == model.dataset_id,
                Dataset.deleted_at.is_(None),
                Dataset.expires_at > now(),
            )
        )
        if dataset is None:
            return False
        snapshot = TrainingSnapshot.model_validate(model.snapshot)
        ids = [example.image_id for example in snapshot.examples]
        count = (
            session.scalar(
                select(func.count())
                .select_from(Image)
                .where(
                    Image.id.in_(ids),
                    Image.dataset_id == model.dataset_id,
                    Image.deleted_at.is_(None),
                )
            )
            or 0
        )
        return count == len(ids)

    def owned(self, session: Session, user: UUID, id: UUID, *, ready: bool = False) -> CustomModel:
        row = session.scalar(
            select(CustomModel).where(CustomModel.id == id, CustomModel.user_id == user)
        )
        if row is None:
            raise DomainError("Model not found", 404)
        if ready and (row.state != "READY" or not self.source_valid(session, row)):
            raise DomainError("Model unavailable, archived or source data deleted/expired", 409)
        return row

    def examples(self, session: Session, dataset: Dataset) -> list[Example]:
        """Valid numerical labels only: annotation photographs, not excluded, score present."""
        rows = session.execute(
            select(Image, Rating)
            .join(Rating)
            .where(
                Image.dataset_id == dataset.id,
                Image.deleted_at.is_(None),
                Image.excluded.is_(False),
                Image.purpose == "annotation",
                Rating.score.is_not(None),
            )
            .order_by(Image.id)
        ).all()
        return [
            Example(
                image_id=image.id,
                artifact_id=image.artifact_id,
                content_hash=image.content_hash,
                score=cast(float, rating.score),
                group=hashlib.sha256(
                    (
                        "subject:" + image.subject_group
                        if image.subject_group
                        else "content:" + image.content_hash
                    ).encode()
                ).hexdigest(),
                subject_known=image.subject_group is not None,
            )
            for image, rating in rows
        ]

    @staticmethod
    def blockers(examples: list[Example], seed: int, fraction: float) -> list[ReadinessReason]:
        """Exactly the submission checks, as stable reason codes for the interface."""
        reasons: list[ReadinessReason] = []
        if len(examples) > 500:
            reasons.append("too_many_ratings")
        if len(examples) < REQUIRED_RATINGS:
            reasons.append("too_few_ratings")
        if len({e.group for e in examples}) < REQUIRED_GROUPS:
            reasons.append("too_few_groups")
        if reasons:
            return reasons
        try:
            training, _ = split_groups([e.group for e in examples], seed, fraction)
        except ValueError:
            return ["insufficient_split"]
        if len({examples[i].score for i in training}) < 2:
            return ["no_score_variation"]
        return []

    def readiness(
        self, user: UUID, dataset_id: UUID, seed: int, fraction: float
    ) -> TrainingReadiness:
        with self.sessions() as session:
            self.data.access(session, user)
            dataset = self.data.dataset(session, user, dataset_id)
            examples = self.examples(session, dataset)
            reasons = self.blockers(examples, seed, fraction)
            if dataset.archived:
                reasons = ["archived", *reasons]
            images = list(
                session.execute(
                    select(Image.excluded, Image.purpose, Rating.image_id, Rating.score)
                    .outerjoin(Rating, Rating.image_id == Image.id)
                    .where(Image.dataset_id == dataset.id, Image.deleted_at.is_(None))
                )
            )
            annotation = [row for row in images if row.purpose == "annotation"]
            return TrainingReadiness(
                eligible=not reasons,
                reasons=reasons,
                rated=len(examples),
                required_ratings=REQUIRED_RATINGS,
                groups=len({e.group for e in examples}),
                required_groups=REQUIRED_GROUPS,
                awaiting=sum(not r.excluded and r.image_id is None for r in annotation),
                skipped=sum(
                    not r.excluded and r.image_id is not None and r.score is None
                    for r in annotation
                ),
                excluded=sum(r.excluded for r in annotation),
                prediction_only=len(images) - len(annotation),
            )

    def train(self, user: UUID, body: TrainRequest) -> ResearchJobView:
        payload: dict[str, JsonValue] = {
            "operation": "train",
            "dataset_id": str(body.dataset_id),
            "alpha": body.alpha,
            "seed": body.seed,
            "validation_fraction": body.validation_fraction,
        }
        # Preserve idempotency of baseline requests submitted before extractor selection existed.
        if body.extractor != EXTRACTOR:
            payload["extractor"] = body.extractor
        with self.sessions.begin() as session:
            self.data.access(session, user, lock=True)
            previous = self.existing(session, user, body.idempotency_key, payload)
            if previous:
                return ResearchJobView.model_validate(previous)
            available, reason = availability(
                body.extractor, self.settings.private_model_root / "pretrained"
            )
            if not available:
                raise DomainError(reason, 503)
            dataset = self.data.dataset(session, user, body.dataset_id, writable=True)
            examples = self.examples(session, dataset)
            reasons = self.blockers(examples, body.seed, body.validation_fraction)
            if "too_many_ratings" in reasons:
                raise DomainError("Training supports at most 500 rated images per version", 422)
            if reasons and reasons != ["no_score_variation"]:
                raise DomainError(
                    "Need 8 rated images, 5 independent groups and 4 training images",
                    422,
                )
            if reasons:
                raise DomainError(
                    "Training split needs at least two distinct numerical scores", 422
                )
            if (
                session.scalar(
                    select(func.count())
                    .select_from(CustomModel)
                    .where(CustomModel.user_id == user, CustomModel.state != "DELETED")
                )
                or 0
            ) >= research_limits(session, user, self.settings).models:
                raise DomainError(
                    "Model version resource limit reached; delete unused versions", 429
                )
            version = (
                session.scalar(
                    select(func.max(CustomModel.version)).where(
                        CustomModel.dataset_id == dataset.id
                    )
                )
                or 0
            ) + 1
            job = self.queue.add_job(
                session, user, "custom", "TRAIN", str(body.idempotency_key), payload
            )
            snapshot = TrainingSnapshot(
                dataset_id=dataset.id,
                consent_version=dataset.consent_version,
                rating_min=dataset.rating_min,
                rating_max=dataset.rating_max,
                examples=examples,
            )
            row = CustomModel(
                user_id=user,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                version=version,
                training_job_id=job.id,
                extractor=body.extractor,
                implementation=IMPLEMENTATION,
                configuration={
                    "extractor": body.extractor,
                    "alpha": body.alpha,
                    "seed": body.seed,
                    "validation_fraction": body.validation_fraction,
                },
                snapshot=snapshot.model_dump(mode="json"),
                snapshot_sha256=digest(snapshot),
                expires_at=dataset.expires_at,
                limitations=[
                    (
                        "Handcrafted visual features; no pretrained facial representation. "
                        if body.extractor == EXTRACTOR
                        else "Frozen ImageNet MobileNetV3-Small; not trained for faces or beauty. "
                    )
                    + "Scores are subjective preferences, not objective beauty.",
                    "Small personal holdout; metrics do not establish reliable generalization.",
                    "Unknown identities can cause leakage; assign person/group IDs.",
                ],
            )
            session.add(row)
            session.flush()
            return ResearchJobView.model_validate(job)

    def predict(self, user: UUID, body: PredictRequest) -> ResearchJobView:
        payload: dict[str, JsonValue] = {
            "operation": "predict",
            "model_id": str(body.model_id),
            "dataset_id": str(body.dataset_id),
            "image_id": str(body.image_id),
        }
        with self.sessions.begin() as session:
            self.data.access(session, user, lock=True)
            previous = self.existing(session, user, body.idempotency_key, payload)
            if previous:
                return ResearchJobView.model_validate(previous)
            self.owned(session, user, body.model_id, ready=True)
            self.data.dataset(session, user, body.dataset_id)
            self.data.image(session, body.dataset_id, body.image_id)
            job = self.queue.add_job(
                session, user, "custom", "SCORE", str(body.idempotency_key), payload
            )
            return ResearchJobView.model_validate(job)

    def view(self, session: Session, row: CustomModel) -> ModelView:
        view = ModelView.model_validate(row)
        job = session.get(ResearchJob, row.training_job_id)
        if view.state == "TRAINING" and job and job.status == "FAILED":
            view.state = "FAILED"
        if view.state != "DELETED" and not self.source_valid(session, row):
            view.state = "DELETED"
        return view

    def list(self, user: UUID) -> list[ModelView]:
        with self.sessions() as session:
            self.data.access(session, user)
            return [
                self.view(session, row)
                for row in session.scalars(
                    select(CustomModel)
                    .where(CustomModel.user_id == user)
                    # Keep every retained version manageable even after many deletions.
                    .order_by((CustomModel.state == "DELETED").asc(), CustomModel.created_at.desc())
                    .limit(research_limits(session, user, self.settings).models + 100)
                )
            ]

    def edit(self, user: UUID, id: UUID, archived: bool) -> ModelView:
        with self.sessions.begin() as session:
            self.data.access(session, user, lock=True)
            row = self.owned(session, user, id)
            if row.state not in {"READY", "ARCHIVED"} or not self.source_valid(session, row):
                raise DomainError("Only completed live models can be archived/restored", 409)
            row.state = "ARCHIVED" if archived else "READY"
            return self.view(session, row)

    def delete(self, user: UUID, id: UUID) -> None:
        with self.sessions.begin() as session:
            session.scalar(select(User).where(User.id == user).with_for_update())
            row = self.owned(session, user, id)
            row.state = "DELETED"
            self.cancel_related(session, row)

    def cancel_related(self, session: Session, model: CustomModel) -> None:
        jobs = session.scalars(
            select(ResearchJob)
            .where(
                ResearchJob.user_id == model.user_id,
                (ResearchJob.id == model.training_job_id)
                | (ResearchJob.payload["model_id"].as_string() == str(model.id)),
            )
            .with_for_update()
        )
        for job in jobs:
            if job.status in {"RUNNING", "QUEUED"}:
                job.status, job.failure_reason, job.phase = (
                    "FAILED",
                    "Model or source data removed",
                    "Failed",
                )
                job.lease_token = None
                job.lease_until = None
                job.completed_at = now()
            job.result = None
            job.payload = None

    def purge(self) -> None:
        with self.sessions() as session:
            candidates = list(
                session.execute(
                    select(CustomModel.id, CustomModel.user_id)
                    .where(
                        (CustomModel.state != "DELETED")
                        | CustomModel.artifact_id.is_not(None)
                        | CustomModel.snapshot["dataset_id"].as_string().is_not(None)
                    )
                    .order_by(CustomModel.created_at)
                )
            )
        for id, owner in candidates:
            with self.sessions.begin() as session:
                session.scalar(select(User).where(User.id == owner).with_for_update())
                model = session.scalar(
                    select(CustomModel).where(CustomModel.id == id).with_for_update()
                )
                if model is None:
                    continue
                job = session.get(ResearchJob, model.training_job_id)
                if model.state == "TRAINING" and job and job.status == "FAILED":
                    model.state = "FAILED"
                if model.state == "DELETED" or not self.source_valid(session, model):
                    model.state = "DELETED"
                    self.cancel_related(session, model)
                    if model.artifact_id:
                        self.store.delete(model.user_id, model.artifact_id)
                    model.artifact_id, model.artifact_sha256 = None, None
                    model.snapshot = {}
                    if model.metrics:
                        model.metrics = {
                            key: value
                            for key, value in model.metrics.items()
                            if key not in {"training_image_ids", "validation_image_ids"}
                        }
        self.purge_orphans()

    def purge_orphans(self) -> None:
        if not self.store.root.exists():
            return
        cutoff = (now() - timedelta(hours=1)).timestamp()
        for directory in self.store.root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                owner = UUID(directory.name)
            except ValueError:
                continue
            with self.sessions.begin() as session:
                session.scalar(select(User).where(User.id == owner).with_for_update())
                live = set(
                    session.scalars(
                        select(CustomModel.artifact_id).where(CustomModel.user_id == owner)
                    )
                )
                for path in directory.iterdir():
                    if not path.is_file() or path.is_symlink():
                        continue
                    try:
                        artifact = UUID(path.name)
                    except ValueError:
                        continue
                    if artifact not in live and path.stat().st_mtime < cutoff:
                        self.store.delete(owner, artifact)
