"""Owner-scoped aesthetic analysis requests on the durable research queue.

Scoring is unavailable unless the operator pinned a checkpoint that passes integrity and
release-gate checks. No result is ever produced without that checkpoint. Credits are not
touched. The private image is removed once its job is final, or after IMAGE_RETENTION.
"""

import logging
from datetime import timedelta
from io import BytesIO
from uuid import UUID, uuid4

import numpy as np
from aevyra_contracts.aesthetic import (
    AestheticAnalysisView,
    AestheticModelCard,
    AestheticResult,
    AestheticStatus,
    AestheticUploadMetadata,
)
from aevyra_inference.aesthetic_checkpoint import SLUG, CheckpointStatus, checkpoint_status
from aevyra_inference.extractors import availability
from PIL import Image
from pydantic import JsonValue, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.aesthetic.models import AestheticAnalysis
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.preferences.images import DecodedImage
from aevyra_api.research.jobs import ResearchQueue, authorized
from aevyra_api.research.models import ResearchJob
from aevyra_api.research.storage import PrivateArtifactStore

logger = logging.getLogger("aevyra.aesthetic")
CONSENT_VERSION = "adult-single-subject-authorized-v1"
IMAGE_RETENTION = timedelta(hours=24)
RESULT_RETENTION = timedelta(days=90)
MIN_EDGE = 224
MAX_ASPECT = 3.0
MIN_LUMINANCE_STD = 4.0
LIMITATIONS = [
    (
        "The score estimates how the model's training annotators rated similar photographs. It is"
        " not objective beauty, worth or health."
    ),
    (
        "Adulthood and a single subject are confirmed by your attestation. Auvylen does not "
        "estimate age from appearance and does not run automated face detection."
    ),
    (
        "Lighting, pose, cropping, expression, image quality and photographic style can change "
        "the score."
    ),
    (
        "Rating spread shows disagreement predicted among annotators. The interval is a separate,"
        " calibrated estimate of the model's own error on held-out people."
    ),
    (
        "The model was validated only on the subjects, annotators and photographs described in "
        "its model card and may not generalize beyond them."
    ),
    (
        "This model is separate from your personal preference models and is not trained on your "
        "ratings."
    ),
]


def suitability(decoded: DecodedImage) -> None:
    """Technical checks only; they cannot establish who or how old the subject is."""
    if min(decoded.width, decoded.height) < MIN_EDGE:
        raise DomainError("Use a photograph at least 224 pixels on its shorter side", 422)
    if max(decoded.width, decoded.height) / min(decoded.width, decoded.height) > MAX_ASPECT:
        raise DomainError("Use a portrait or square photograph (aspect ratio up to 3:1)", 422)
    with Image.open(BytesIO(decoded.thumbnail)) as thumbnail:
        luminance = np.asarray(thumbnail.convert("L"), dtype=np.float64)
    if float(luminance.std()) < MIN_LUMINANCE_STD:
        raise DomainError("The photograph appears blank; use a clear photograph of one adult", 422)


class AestheticService:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions = sessions
        self.settings = settings
        # Separate private namespace; never mounted in web/proxy containers.
        self.store = PrivateArtifactStore(settings.private_upload_root / "aesthetic")
        self.queue = ResearchQueue(sessions, settings)

    def checkpoint(self) -> CheckpointStatus:
        settings = self.settings
        status = checkpoint_status(
            settings.private_model_root,
            settings.aesthetic_model_version,
            settings.aesthetic_manifest_sha256,
            enabled=settings.aesthetic_scoring_enabled,
            allow_synthetic=settings.aesthetic_allow_synthetic_test_checkpoint,
        )
        if status.available and status.checkpoint is not None:
            ready, _ = availability(
                status.checkpoint.manifest.extractor, settings.private_model_root / "pretrained"
            )
            if not ready:
                return CheckpointStatus(False, "extractor_unavailable", status.checkpoint)
        return status

    def access(self, session: Session, user: UUID, *, lock: bool = False) -> None:
        if lock:
            session.scalar(select(User).where(User.id == user).with_for_update())
        if not self.settings.research_mode or not authorized(session, user):
            raise DomainError("Research access required", 403)

    def status(self, user: UUID) -> AestheticStatus:
        with self.sessions() as session:
            allowed = self.settings.research_mode and authorized(session, user)
        status = self.checkpoint()
        card = None
        if status.available and status.checkpoint is not None:
            item = status.checkpoint.manifest
            metrics = item.metrics
            try:
                card = AestheticModelCard.model_validate(
                    {
                        "model_version": item.model_version,
                        "calibration_version": item.calibration.version,
                        "implementation": item.implementation,
                        "extractor": item.extractor,
                        "dataset_name": item.dataset.name,
                        "dataset_license": item.dataset.license,
                        "annotator_population": item.dataset.annotator_population,
                        "synthetic": item.dataset.synthetic,
                        "interval_level": item.calibration.level,
                        "interval_half_width": item.calibration.half_width_display,
                        "interval_test_coverage": item.calibration.test_coverage,
                        **{
                            key: metrics.get(key)
                            for key in (
                                "test_images",
                                "test_subjects",
                                "test_mae",
                                "mean_baseline_mae",
                                "test_spearman",
                                "test_distribution_loss",
                                "mean_distribution_baseline_loss",
                            )
                        },
                    }
                )
            except ValidationError:
                status = CheckpointStatus(False, "checkpoint_integrity_failure")
        return AestheticStatus(
            enabled=self.settings.aesthetic_scoring_enabled,
            authorized=allowed,
            available=status.available and card is not None,
            reason=status.reason,
            model=card,
            limitations=LIMITATIONS,
        )

    def ready(self) -> CheckpointStatus:
        status = self.checkpoint()
        if not status.available or status.checkpoint is None:
            raise DomainError("Aesthetic scoring unavailable: no validated model is installed", 503)
        return status

    def check_submit(self, user: UUID) -> None:
        with self.sessions() as session:
            self.access(session, user)
        self.ready()

    def view(self, session: Session, row: AestheticAnalysis) -> AestheticAnalysisView:
        # Include idempotent submission retries, not only GET/list responses.
        if row.expires_at.replace(tzinfo=now().tzinfo) <= now():
            raise DomainError("Analysis not found", 404)
        job = session.get(ResearchJob, row.job_id)
        if job is None:
            raise DomainError("Analysis not found", 404)
        result = None
        if job.status == "COMPLETED" and job.result is not None:
            result = AestheticResult.model_validate(job.result)
        return AestheticAnalysisView(
            id=row.id,
            status=job.status,  # type: ignore[arg-type]  # Constrained by ck_job_status.
            progress=job.progress,
            phase=job.phase,
            failure_reason=job.failure_reason,
            model_version=row.model_version,
            image_retained=row.artifact_id is not None,
            result=result,
            created_at=row.created_at,
            completed_at=job.completed_at,
        )

    def submit(
        self, user: UUID, metadata: AestheticUploadMetadata, decoded: DecodedImage
    ) -> AestheticAnalysisView:
        key = str(metadata.idempotency_key)
        with self.sessions() as session:
            previous = session.scalar(
                select(AestheticAnalysis).where(
                    AestheticAnalysis.user_id == user, AestheticAnalysis.request_key == key
                )
            )
            if previous is not None and previous.deleted_at is None:
                return self.view(session, previous)
        suitability(decoded)
        loaded = self.ready().checkpoint
        assert loaded is not None
        artifact: UUID | None = None
        try:
            with self.sessions.begin() as session:
                self.access(session, user, lock=True)
                existing = session.scalar(
                    select(AestheticAnalysis).where(
                        AestheticAnalysis.user_id == user, AestheticAnalysis.request_key == key
                    )
                )
                if existing is not None:
                    if existing.deleted_at is not None:
                        raise DomainError("Analysis request key already used", 409)
                    return self.view(session, existing)
                if session.scalar(
                    select(ResearchJob.id).where(
                        ResearchJob.user_id == user, ResearchJob.request_key == key
                    )
                ):
                    raise DomainError("Research request key conflict", 409)
                analysis_id = uuid4()
                payload: dict[str, JsonValue] = {
                    "operation": "aesthetic_score",
                    "analysis_id": str(analysis_id),
                }
                job = self.queue.add_job(session, user, SLUG, "SCORE", key, payload)
                artifact, sha256 = self.store.put(user, decoded.image)
                row = AestheticAnalysis(
                    id=analysis_id,
                    user_id=user,
                    job_id=job.id,
                    request_key=key,
                    artifact_id=artifact,
                    image_sha256=sha256,
                    width=decoded.width,
                    height=decoded.height,
                    consent_version=CONSENT_VERSION,
                    model_version=loaded.manifest.model_version,
                    manifest_sha256=loaded.manifest_sha256,
                    created_at=now(),
                    expires_at=now() + RESULT_RETENTION,
                )
                session.add(row)
                session.flush()
                return self.view(session, row)
        except Exception:
            if artifact is not None:
                try:
                    self.store.delete(user, artifact)
                except OSError as exc:
                    logger.error(
                        "aesthetic_rollback_cleanup_failed",
                        extra={"error_type": type(exc).__name__},
                    )
            raise

    def owned(self, session: Session, user: UUID, id: UUID) -> AestheticAnalysis:
        row = session.scalar(
            select(AestheticAnalysis).where(
                AestheticAnalysis.id == id,
                AestheticAnalysis.user_id == user,
                AestheticAnalysis.deleted_at.is_(None),
            )
        )
        if row is None:
            raise DomainError("Analysis not found", 404)
        return row

    def get(self, user: UUID, id: UUID) -> AestheticAnalysisView:
        with self.sessions() as session:
            self.access(session, user)
            return self.view(session, self.owned(session, user, id))

    def list(self, user: UUID) -> list[AestheticAnalysisView]:
        with self.sessions() as session:
            self.access(session, user)
            rows = session.scalars(
                select(AestheticAnalysis)
                .where(
                    AestheticAnalysis.user_id == user,
                    AestheticAnalysis.deleted_at.is_(None),
                    AestheticAnalysis.expires_at > now(),
                )
                .order_by(AestheticAnalysis.created_at.desc())
                .limit(50)
            )
            return [self.view(session, row) for row in rows]

    def delete(self, user: UUID, id: UUID) -> None:
        # Owners keep deletion rights even after research access is revoked.
        with self.sessions.begin() as session:
            session.scalar(select(User).where(User.id == user).with_for_update())
            row = self.owned(session, user, id)
            job = session.scalar(
                select(ResearchJob).where(ResearchJob.id == row.job_id).with_for_update()
            )
            if job is not None:
                if job.status in {"QUEUED", "RUNNING"}:
                    job.status, job.phase = "FAILED", "Cancelled"
                    job.failure_reason = "Deleted by owner"
                    job.completed_at = now()
                    job.lease_token = job.lease_until = None
                job.result = None
            row.deleted_at = now()
        self.purge()

    def discard_image(self, id: UUID) -> None:
        """Delete the file first; the reference is cleared only once the file is gone."""
        with self.sessions.begin() as session:
            row = session.scalar(
                select(AestheticAnalysis).where(AestheticAnalysis.id == id).with_for_update()
            )
            if row is None or row.artifact_id is None:
                return
            self.store.delete(row.user_id, row.artifact_id)
            row.artifact_id = None

    def purge(self) -> int:
        """Retryable retention: final/stale images, then deleted or expired results."""
        removed = 0
        stale = now() - IMAGE_RETENTION
        with self.sessions.begin() as session:
            rows = list(
                session.scalars(
                    select(AestheticAnalysis)
                    .join(ResearchJob, ResearchJob.id == AestheticAnalysis.job_id)
                    .where(
                        or_(
                            AestheticAnalysis.deleted_at.is_not(None),
                            AestheticAnalysis.expires_at <= now(),
                            (AestheticAnalysis.artifact_id.is_not(None))
                            & (
                                ResearchJob.status.in_(["COMPLETED", "FAILED"])
                                | (AestheticAnalysis.created_at <= stale)
                            ),
                        )
                    )
                    .order_by(AestheticAnalysis.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(50)
                )
            )
            for row in rows:
                if row.artifact_id is not None:
                    self.store.delete(row.user_id, row.artifact_id)
                    row.artifact_id = None
                    removed += 1
                expired = session.scalar(
                    select(AestheticAnalysis.id).where(
                        AestheticAnalysis.id == row.id,
                        or_(
                            AestheticAnalysis.deleted_at.is_not(None),
                            AestheticAnalysis.expires_at <= now(),
                        ),
                    )
                )
                if expired is not None:
                    job = session.get(ResearchJob, row.job_id)
                    if job is not None:
                        if job.status in {"QUEUED", "RUNNING"}:
                            job.status, job.phase = "FAILED", "Expired"
                            job.failure_reason = "Analysis expired or deleted"
                            job.completed_at = now()
                            job.lease_token = job.lease_until = None
                        job.result = None
                    session.delete(row)
        self.purge_orphans()
        return removed

    def purge_orphans(self) -> None:
        """Recover files left by process death before the submission committed."""
        if not self.store.root.exists():
            return
        cutoff = (now() - timedelta(hours=1)).timestamp()
        for directory in self.store.root.iterdir():
            if directory.is_symlink() or not directory.is_dir():
                continue
            try:
                owner = UUID(directory.name)
            except ValueError:
                continue
            with self.sessions.begin() as session:
                # Submissions hold the same user lock while creating files.
                session.scalar(select(User).where(User.id == owner).with_for_update())
                live = set(
                    session.scalars(
                        select(AestheticAnalysis.artifact_id).where(
                            AestheticAnalysis.user_id == owner,
                            AestheticAnalysis.artifact_id.is_not(None),
                        )
                    )
                )
                for path in directory.iterdir():
                    if path.is_symlink() or not path.is_file():
                        continue
                    try:
                        artifact = UUID(path.name)
                    except ValueError:
                        continue
                    if artifact not in live and path.stat().st_mtime < cutoff:
                        self.store.delete(owner, artifact)
