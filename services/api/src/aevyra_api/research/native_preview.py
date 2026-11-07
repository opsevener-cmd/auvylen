"""Owner-only laboratory upload, queue and retention. No consumer gate is bypassed."""

import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
from uuid import UUID

from aevyra_contracts.aesthetic import AestheticUploadMetadata
from aevyra_contracts.native_preview import NativePreviewResult
from aevyra_contracts.research import ResearchJobView
from aevyra_inference.extractors import availability
from aevyra_inference.native_checkpoint import SLUG, Manifest, release_failures
from aevyra_inference.native_preview import reviewed
from PIL import Image, ImageOps
from pydantic import JsonValue
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from aevyra_api.accounts import session_digest
from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.codes import aware
from aevyra_api.credits.models import AccountSession, User
from aevyra_api.entitlements import require_owner
from aevyra_api.preferences.images import decode_image_bytes
from aevyra_api.research.jobs import JobLease, ResearchQueue
from aevyra_api.research.lease import LeaseHeartbeat
from aevyra_api.research.models import ResearchJob
from aevyra_api.research.storage import PrivateArtifactStore

OPERATION = "native_research_preview"
IMAGE_TTL = timedelta(hours=1)
RESULT_TTL = timedelta(hours=24)


def is_preview(job: ResearchJob) -> bool:
    return job.provider == SLUG and (job.payload or {}).get("operation") == OPERATION


def model_context(item: Manifest) -> dict[str, JsonValue]:
    """Aggregate provenance and held-out evidence recorded at training time.

    These are the checkpoint's own recorded numbers, shown so a 1–7 prediction can be read
    against the model's typical error. They are aggregate, not an interval for one portrait.
    """
    report = item.report

    def metric(section: str, key: str) -> JsonValue:
        value = (report.get(section) or {}).get(key)
        return value if isinstance(value, int | float) and math.isfinite(value) else None

    counts = report.get("subject_counts") or {}
    return {
        "trained_at": item.created_at,
        "selection_protocol": report.get("selection_protocol", "validation-3"),
        "training_subjects": counts.get("train"),
        "heldout_subjects": counts.get("test"),
        "heldout_mae": metric("test", "mae"),
        "heldout_spearman": metric("test", "spearman"),
        "baseline_mae": metric("mean_baseline", "mae"),
    }


def canonical(payload: bytes) -> bytes:
    decode_image_bytes(payload)  # Existing decompression, dimensions and format bounds.
    # Preserve oriented RGB pixels for inference parity; no JPEG re-encoding or metadata.
    with Image.open(BytesIO(payload), formats=["JPEG", "PNG"]) as image:
        rgb = ImageOps.exif_transpose(image).convert("RGB")
        if min(rgb.size) < 224:
            raise DomainError("Use a photograph at least 224 pixels on its shorter side", 422)
        rgb.info.clear()
        output = BytesIO()
        rgb.save(output, format="PNG")
    return output.getvalue()


class NativePreview:
    def __init__(self, sessions: sessionmaker[Session], settings: Settings):
        self.sessions, self.settings = sessions, settings
        self.queue = ResearchQueue(sessions, settings)
        self.store = PrivateArtifactStore(
            settings.private_upload_root / "native-preview", 50 * 1024**2
        )

    def access(
        self, session: Session, user: UUID, *, token: str | None = None, lock: bool = True
    ) -> None:
        # Mutations lock the Owner row; the read-only status check must not serialize on it.
        query = select(User).where(User.id == user)
        require_owner(session.scalar(query.with_for_update() if lock else query))
        if token is not None:
            auth = session.scalar(
                select(AccountSession).where(
                    AccountSession.user_id == user,
                    AccountSession.token_digest == session_digest(token),
                )
            )
            if auth is None or aware(auth.expires_at) <= now():
                raise DomainError("Sign in required", 401)
            if aware(auth.created_at) < now() - timedelta(
                seconds=self.settings.owner_fresh_auth_seconds
            ):
                raise DomainError("Fresh Owner sign-in required for this operation", 403)

    def ready(self) -> Manifest:
        s = self.settings
        if (
            not s.native_preview_enabled
            or not s.research_mode
            or s.public_pilot
            or s.api_environment not in {"development", "test"}
            or not s.native_preview_checkpoint
            or not s.native_preview_manifest_sha256
            or not (s.native_preview_review_reference or "").strip()
        ):
            raise DomainError("Native research preview disabled", 503)
        try:
            item = reviewed(s.native_preview_checkpoint, s.native_preview_manifest_sha256)
            if not availability(item.encoder, s.private_model_root / "pretrained")[0]:
                raise ValueError("Encoder unavailable")
            return item
        except (ValueError, OSError):
            raise DomainError("Native research checkpoint unavailable or invalid", 503) from None

    def check_submit(self, user: UUID, token: str) -> None:
        with self.sessions() as session:
            self.access(session, user, token=token)
        self.ready()

    def status(self, user: UUID) -> dict[str, JsonValue]:
        with self.sessions() as session:
            self.access(session, user, lock=False)
        try:
            item = self.ready()
        except DomainError:
            return {"available": False, "consumer_enabled": False, "native_scale": [1, 7]}
        return {
            "available": True,
            "consumer_enabled": False,
            "native_scale": [1, 7],
            "manifest_sha256": self.settings.native_preview_manifest_sha256,
            "collection": item.collection.name,
            "encoder": item.encoder,
            "release_failures": list[JsonValue](release_failures(item)),
            "model": model_context(item),
        }

    def submit(
        self, user: UUID, token: str, meta: AestheticUploadMetadata, image: bytes
    ) -> ResearchJobView:
        self.ready()
        self.purge()
        digest = hashlib.sha256(image).hexdigest()
        with self.sessions.begin() as session:
            self.access(session, user, token=token)
            previous = session.scalar(
                select(ResearchJob).where(
                    ResearchJob.user_id == user,
                    ResearchJob.request_key == str(meta.idempotency_key),
                )
            )
            if previous:
                p = previous.payload or {}
                if (
                    not is_preview(previous)
                    or p.get("sha256") != digest
                    or p.get("pin") != self.settings.native_preview_manifest_sha256
                ):
                    raise DomainError("Research request key conflict", 409)
                return ResearchJobView.model_validate(previous)
            artifact, _ = self.store.put(user, image)
            try:
                job = self.queue.add_job(
                    session,
                    user,
                    SLUG,
                    "SCORE",
                    str(meta.idempotency_key),
                    {
                        "operation": OPERATION,
                        "artifact": str(artifact),
                        "sha256": digest,
                        "pin": self.settings.native_preview_manifest_sha256,
                        "review": self.settings.native_preview_review_reference,
                        "consent": "adult-single-subject-research-preview-v1",
                    },
                )
                view = ResearchJobView.model_validate(job)
                session.flush()
            except Exception:
                self.store.delete(user, artifact)
                raise
        return view

    def owned(self, session: Session, user: UUID, job_id: UUID) -> ResearchJob:
        self.access(session, user)
        job = session.scalar(
            select(ResearchJob)
            .where(ResearchJob.id == job_id, ResearchJob.user_id == user)
            .with_for_update()
        )
        if job is None or not is_preview(job) or (job.payload or {}).get("deleted"):
            raise DomainError("Research job not found", 404)
        return job

    def history(self, user: UUID, limit: int = 20) -> list[ResearchJobView]:
        """The Owner's own retained previews, newest first; retention is applied first."""
        with self.sessions.begin() as session:
            self.access(session, user)
            jobs = session.scalars(
                select(ResearchJob)
                .where(ResearchJob.user_id == user, ResearchJob.provider == SLUG)
                .where(ResearchJob.payload["deleted"].as_boolean().is_(None))
                .order_by(ResearchJob.created_at.desc())
                .limit(limit)
                .with_for_update()
            )
            views = []
            for job in jobs:
                if not is_preview(job):
                    continue
                self.expire(job)
                if not (job.payload or {}).get("deleted"):
                    views.append(ResearchJobView.model_validate(job))
        return views

    def get(self, user: UUID, job_id: UUID) -> ResearchJobView:
        # Polling expires only the requested job. The worker's periodic purge() owns the
        # global sweep and orphan cleanup, so a poll never scans every Owner's jobs.
        with self.sessions.begin() as session:
            job = self.owned(session, user, job_id)
            self.expire(job)
            view = ResearchJobView.model_validate(job)
            expired = bool((job.payload or {}).get("deleted"))
        if expired:
            raise DomainError("Research job not found", 404)
        return view

    def erase(self, job: ResearchJob, *, expired: bool = False) -> None:
        payload = dict(job.payload or {})
        if payload.get("artifact"):
            self.store.delete(job.user_id, UUID(str(payload.pop("artifact"))))
        if expired:
            job.status, job.phase = "FAILED", "Expired"
            job.failure_reason = "Native preview expired or removed"
            job.completed_at = now()
            job.result = None
            job.lease_token = job.lease_until = None
            payload = {"operation": OPERATION, "deleted": True}
        job.payload = payload

    def expire(self, job: ResearchJob) -> None:
        """Apply image and result retention to one locked job; idempotent."""
        if not is_preview(job) or (job.payload or {}).get("deleted"):
            return
        age = now() - aware(job.created_at)
        if age >= RESULT_TTL or (job.status in {"QUEUED", "RUNNING"} and age >= IMAGE_TTL):
            self.erase(job, expired=True)
        elif job.status in {"COMPLETED", "FAILED"} and (job.payload or {}).get("artifact"):
            self.erase(job)

    def delete(self, user: UUID, job_id: UUID) -> None:
        with self.sessions.begin() as session:
            self.erase(self.owned(session, user, job_id), expired=True)

    def purge(self) -> None:
        # Deleted tombstones are excluded; no personal dataset access.
        with self.sessions.begin() as session:
            for job in session.scalars(
                select(ResearchJob)
                .where(ResearchJob.provider == SLUG)
                .where(ResearchJob.payload["deleted"].as_boolean().is_(None))
                .where(
                    or_(
                        ResearchJob.created_at <= now() - IMAGE_TTL,
                        ResearchJob.status.in_(["COMPLETED", "FAILED"]),
                    )
                )
                .with_for_update()
            ):
                self.expire(job)
        # A crash/failed commit after put() must not leave an eternal orphan.
        if self.store.root.exists():
            for owner in self.store.root.iterdir():
                if owner.is_symlink() or not owner.is_dir():
                    continue
                for artifact in owner.iterdir():
                    if artifact.is_symlink() or not artifact.is_file():
                        continue
                    if artifact.stat().st_mtime <= now().timestamp() - IMAGE_TTL.total_seconds():
                        try:
                            self.store.delete(UUID(owner.name), UUID(artifact.name))
                        except ValueError:
                            continue

    def execute(self, lease: JobLease, heartbeat: LeaseHeartbeat) -> bool:
        self.ready()
        with self.sessions() as session:
            job = self.owned(session, lease.user_id, lease.id)
            payload = dict(job.payload or {})
            if now() - aware(job.created_at) >= IMAGE_TTL:
                raise ValueError("Preview upload expired")
        pin = self.settings.native_preview_manifest_sha256
        if (
            payload.get("pin") != pin
            or payload.get("review") != self.settings.native_preview_review_reference
        ):
            raise ValueError("Preview review changed")
        artifact = UUID(str(payload["artifact"]))
        image = self.store.read(lease.user_id, artifact)
        if hashlib.sha256(image).hexdigest() != payload["sha256"]:
            raise ValueError("Private image integrity failure")
        heartbeat.check()
        if not self.queue.progress(lease, 10, "Running native research preview"):
            raise ValueError("Preview lease lost")
        args = {
            "checkpoint": str(self.settings.native_preview_checkpoint),
            "pin": pin,
            "encoder_root": str(self.settings.private_model_root / "pretrained"),
            "image": str(self.store._path(lease.user_id, artifact)),
        }
        process = subprocess.run(
            [sys.executable, "-m", "aevyra_inference.native_preview"],
            input=json.dumps(args),
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"},
            check=False,
        )
        if process.returncode != 0 or len(process.stdout) > 16384:
            raise ValueError("Native preview execution failed")
        result = NativePreviewResult.model_validate_json(process.stdout)
        if result.input_check.verdict == "unchecked" and result.predicted_rating is not None:
            raise ValueError("New scores require a supported input check")
        if result.manifest_sha256 != pin:
            raise ValueError("Native preview checkpoint mismatch")
        heartbeat.check()

        def verify(session: Session) -> None:
            current = self.owned(session, lease.user_id, lease.id)
            if (
                now() - aware(current.created_at) >= IMAGE_TTL
                or self.settings.native_preview_manifest_sha256 != pin
                or self.settings.native_preview_review_reference != payload.get("review")
            ):
                raise ValueError("Native preview expired or its review changed")
            self.ready()  # Recheck capability, integrity and rights before publishing.

        return self.queue.finish(lease, result.model_dump(mode="json"), verify)
