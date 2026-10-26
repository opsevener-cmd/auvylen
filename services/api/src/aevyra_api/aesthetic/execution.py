"""Aesthetic scoring runs only in the leased worker; completion is fenced by the queue."""

import hashlib
import logging
import time

from aevyra_contracts.aesthetic import AestheticResult
from aevyra_inference.aesthetic_checkpoint import SLUG, AestheticScoringEngine
from aevyra_inference.engine import EngineRegistry
from aevyra_inference.extractors import create_extractor
from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from aevyra_api.aesthetic.models import AestheticAnalysis
from aevyra_api.aesthetic.service import AestheticService
from aevyra_api.commercial.state import DomainError
from aevyra_api.research.jobs import JobLease, ResearchQueue
from aevyra_api.research.lease import LeaseHeartbeat
from aevyra_api.research.models import ResearchJob

logger = logging.getLogger("aevyra.worker")


class AestheticExecution:
    def __init__(self, queue: ResearchQueue, lease: JobLease, heartbeat: LeaseHeartbeat):
        self.queue, self.lease, self.heartbeat = queue, lease, heartbeat
        self.service = AestheticService(queue.sessions, queue.settings)

    def check(self, percent: int, phase: str) -> None:
        self.heartbeat.check()
        if not self.queue.progress(self.lease, percent, phase):
            raise RuntimeError("Aesthetic job cancelled, expired or revoked")

    def analysis(self, session: Session) -> AestheticAnalysis:
        job = session.get(ResearchJob, self.lease.id)
        row = session.scalar(
            select(AestheticAnalysis).where(
                AestheticAnalysis.job_id == self.lease.id,
                AestheticAnalysis.user_id == self.lease.user_id,
                AestheticAnalysis.deleted_at.is_(None),
            )
        )
        if (
            job is None
            or job.payload is None
            or row is None
            or job.payload.get("analysis_id") != str(row.id)
        ):
            raise DomainError("Analysis request unavailable", 409)
        return row

    def score(self) -> bool:
        started = time.monotonic()
        with self.queue.sessions() as session:
            row = self.analysis(session)
            if row.artifact_id is None:
                raise DomainError("Analysis image already removed", 409)
            payload = self.service.store.read(self.lease.user_id, row.artifact_id)
            analysis_id, manifest_sha256 = row.id, row.manifest_sha256
            image_sha256 = row.image_sha256
        if hashlib.sha256(payload).hexdigest() != image_sha256:
            raise ValueError("Analysis image integrity failure")
        # Re-verify the pinned checkpoint and gate at execution time; never use a stale load.
        loaded = self.service.ready().checkpoint
        assert loaded is not None
        if loaded.manifest_sha256 != manifest_sha256:
            raise DomainError("Model changed after submission; submit the photograph again", 409)
        self.check(10, "Extracting visual features")
        extractor = create_extractor(
            loaded.manifest.extractor, self.queue.settings.private_model_root / "pretrained"
        )
        features = extractor.extract_batch([payload])[0]
        self.check(70, "Scoring rating distribution")
        engine = AestheticScoringEngine(loaded, features, release_ready=True)
        score = EngineRegistry([engine]).score(
            SLUG,
            payload,
            production=self.queue.settings.api_environment == "production",
            purpose="research",
        )
        analysis = engine.analysis()
        calibration = loaded.manifest.calibration
        half = calibration.half_width_display
        result: dict[str, JsonValue] = score.model_dump(mode="json")
        result.update(analysis)
        result.update(
            {
                "calibration_version": calibration.version,
                "interval_level": calibration.level,
                "interval_low": None if half is None else max(1.0, analysis["score_10"] - half),
                "interval_high": None if half is None else min(10.0, analysis["score_10"] + half),
                "extractor": loaded.manifest.extractor,
                "processing_duration_ms": (time.monotonic() - started) * 1000,
                "adult_basis": "user_attestation",
                "single_subject_basis": "user_attestation",
                "automated_face_detection": "not_implemented",
            }
        )
        AestheticResult.model_validate(result)  # Never publish an unverifiable result.
        self.check(95, "Saving result")

        def verify(session: Session) -> None:
            current = session.scalar(
                select(AestheticAnalysis)
                .where(AestheticAnalysis.id == analysis_id, AestheticAnalysis.deleted_at.is_(None))
                .with_for_update()
            )
            if current is None:
                raise DomainError("Analysis deleted before completion", 409)

        saved = self.queue.finish(self.lease, result, verify)
        if saved:
            self.service.discard_image(analysis_id)
        return saved

    def fail(self) -> None:
        # Remove the image only once the fenced queue has made the job final; a lost
        # lease leaves the image for the worker that now owns the retry.
        with self.queue.sessions() as session:
            job = session.get(ResearchJob, self.lease.id)
            row = session.scalar(
                select(AestheticAnalysis).where(AestheticAnalysis.job_id == self.lease.id)
            )
            final = job is not None and job.status in {"COMPLETED", "FAILED"}
        if final and row is not None:
            self.service.discard_image(row.id)
