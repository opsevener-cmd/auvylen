"""Private pretrained comparisons on the existing fenced research queue. No Credits."""

import hashlib
import json
import math
import os
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
from urllib.parse import unquote
from uuid import UUID

from aevyra_contracts import ScoringResult
from aevyra_contracts.aesthetic import AestheticUploadMetadata
from aevyra_contracts.commercial import EmptyRequest
from aevyra_contracts.research import ProviderView, ResearchJobView, ResearchStatus
from aevyra_inference.providers import ProviderCatalog
from fastapi import APIRouter, Depends, Request
from PIL import Image, ImageOps
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from aevyra_api.commercial.models import now
from aevyra_api.commercial.state import DomainError
from aevyra_api.config import Settings
from aevyra_api.credits.models import User
from aevyra_api.preferences.images import MAX_UPLOAD_BYTES, decode_image_bytes
from aevyra_api.research.jobs import JobLease, ResearchQueue, authorized
from aevyra_api.research.lease import LeaseHeartbeat
from aevyra_api.research.models import ResearchJob
from aevyra_api.research.storage import PrivateArtifactStore
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions
from aevyra_api.routes.preferences import upload_slots

router = APIRouter(prefix="/api/v1/research/pretrained", tags=["pretrained research"])


def catalog(settings: Settings) -> ProviderCatalog:
    return ProviderCatalog(settings.enabled_model_providers, settings.private_model_root)


def store(settings: Settings) -> PrivateArtifactStore:
    return PrivateArtifactStore(settings.private_upload_root / "pretrained")


def access(session: Session, settings: Settings, user: UUID) -> None:
    if not settings.research_mode or not authorized(session, user):
        raise DomainError("Research access required", 403)
    # Production requires a separate release review; never enabled by a commercial flag.
    if settings.api_environment in {"staging", "production"}:
        raise DomainError("Pretrained deployment has not been approved", 503)


def ready(settings: Settings) -> None:
    if not catalog(settings).status("comboloss").available:
        raise DomainError("Pretrained checkpoint, dependencies or research rights unavailable", 503)


def submit_image(
    request: Request, user: User, metadata: AestheticUploadMetadata, image: bytes
) -> ResearchJobView:
    settings = config(request)
    artifact = None
    private = store(settings)
    try:
        with sessions(request).begin() as session:
            session.scalar(select(User).where(User.id == user.id).with_for_update())
            access(session, settings, user.id)
            ready(settings)
            existing = session.scalar(
                select(ResearchJob).where(
                    ResearchJob.user_id == user.id,
                    ResearchJob.request_key == str(metadata.idempotency_key),
                )
            )
            if existing:
                if existing.provider != "comboloss":
                    raise DomainError("Research request key conflict", 409)
                return ResearchJobView.model_validate(existing)
            artifact, digest = private.put(user.id, image)
            job = ResearchQueue(sessions(request), settings).add_job(
                session,
                user.id,
                "comboloss",
                "SCORE",
                str(metadata.idempotency_key),
                {
                    "artifact": str(artifact),
                    "image_sha256": digest,
                    "consent_version": "adult-single-subject-authorized-v1",
                    "manifest_sha256": os.environ.get("COMBOLOSS_MANIFEST_SHA256", ""),
                },
            )
            return ResearchJobView.model_validate(job)
    except Exception:
        if artifact is not None:
            private.delete(user.id, artifact)
        raise


@router.post(
    "/comboloss", response_model=ResearchJobView, status_code=202, dependencies=[Depends(csrf)]
)
async def submit(request: Request, user: CurrentUser) -> ResearchJobView:
    settings = config(request)
    with sessions(request)() as session:
        access(session, settings, user.id)
    await run_in_threadpool(ready, settings)
    rate(request, "analysis", 30, user.public_user_id)
    if request.headers.get("content-type") not in {"image/jpeg", "image/png"}:
        raise DomainError("Upload a JPEG or PNG photograph", 415)
    header = request.headers.get("x-upload-metadata", "")
    try:
        if len(header) > 1024:
            raise ValueError
        metadata = AestheticUploadMetadata.model_validate_json(unquote(header, errors="strict"))
    except (ValidationError, UnicodeError, ValueError):
        raise DomainError("Confirm adult, single-subject and authorization consent", 422) from None
    if not upload_slots.acquire(blocking=False):
        raise DomainError("Image processing busy; retry shortly", 429)
    try:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_UPLOAD_BYTES:
                raise DomainError("Image exceeds 4 MiB limit", 413)
            payload.extend(chunk)
        image = await run_in_threadpool(canonical, bytes(payload))
        return await run_in_threadpool(submit_image, request, user, metadata, image)
    finally:
        upload_slots.release()


def canonical(payload: bytes) -> bytes:
    decode_image_bytes(payload)  # Existing decompression, format and resolution limits.
    with Image.open(BytesIO(payload)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        if min(image.size) < 224:
            raise DomainError("Use a photograph at least 224 pixels on its shorter side", 422)
        image.info.clear()
        buffer = BytesIO()
        image.save(buffer, format="PNG")
    if len(buffer.getvalue()) > 10 * 1024 * 1024:
        raise DomainError("Decoded image exceeds private storage limit", 413)
    return buffer.getvalue()


def purge_pretrained(queue: ResearchQueue) -> None:
    """Remove final images and expire results after 24 hours, including revoked users."""
    with queue.sessions.begin() as session:
        rows = session.scalars(
            select(ResearchJob)
            .where(ResearchJob.provider == "comboloss")
            .with_for_update(skip_locked=True)
        )
        for job in rows:
            expired = job.created_at.replace(tzinfo=now().tzinfo) < now() - timedelta(hours=24)
            if expired:
                job.status, job.phase, job.result = "FAILED", "Expired", None
                job.lease_token = job.lease_until = None
            if expired or job.status in {"COMPLETED", "FAILED"}:
                if job.payload and job.payload.get("artifact"):
                    store(queue.settings).delete(job.user_id, UUID(str(job.payload["artifact"])))
                    job.payload = None
    # Crash before DB commit: all files have a hard 24-hour ceiling; UUID-only paths.
    root = store(queue.settings).root
    if root.exists():
        for owner in root.iterdir():
            if owner.is_symlink() or not owner.is_dir():
                continue
            for path in owner.iterdir():
                if (
                    not path.is_symlink()
                    and path.is_file()
                    and path.stat().st_mtime < (now() - timedelta(hours=24)).timestamp()
                ):
                    store(queue.settings).delete(UUID(owner.name), UUID(path.name))


def execute_pretrained(queue: ResearchQueue, lease: JobLease, heartbeat: LeaseHeartbeat) -> None:
    settings = queue.settings
    with queue.sessions() as session:
        access(session, settings, lease.user_id)
        job = session.get(ResearchJob, lease.id)
        if job is None or not job.payload:
            raise ValueError("Missing private image")
        payload = job.payload
    ready(settings)
    if payload.get("manifest_sha256") != os.environ.get("COMBOLOSS_MANIFEST_SHA256", ""):
        raise ValueError("Model changed since submission")
    image = store(settings).read(lease.user_id, UUID(str(payload["artifact"])))
    if hashlib.sha256(image).hexdigest() != payload["image_sha256"]:
        raise ValueError("Image integrity failure")
    heartbeat.check()
    # The child is killable; heavyweight imports/model state never enter the API or worker.
    process = subprocess.run(
        [sys.executable, "-m", "auvylen_comboloss", str(settings.private_model_root / "comboloss")],
        input=image,
        capture_output=True,
        timeout=90,
        check=True,
    )
    if len(process.stdout) > 16384:
        raise ValueError("Invalid model response")
    result = json.loads(process.stdout)
    if result.get("engine") != "comboloss" or result.get("synthetic") is not False:
        raise ValueError("Invalid model identity")
    validated = ScoringResult.model_validate(result)
    if not math.isfinite(validated.raw_score) or result.get("native_scale") != [1, 5]:
        raise ValueError("Invalid native score")
    heartbeat.check()
    queue.finish(lease, result)


@router.post("/jobs/{job_id}/delete", dependencies=[Depends(csrf)])
def delete(
    job_id: UUID, body: EmptyRequest, request: Request, user: CurrentUser
) -> dict[str, bool]:
    with sessions(request).begin() as session:
        session.scalar(select(User).where(User.id == user.id).with_for_update())
        job = session.scalar(
            select(ResearchJob)
            .where(
                ResearchJob.id == job_id,
                ResearchJob.user_id == user.id,
                ResearchJob.provider == "comboloss",
            )
            .with_for_update()
        )
        if job is None:
            raise DomainError("Research job not found", 404)
        job.status, job.phase, job.result = "FAILED", "Deleted", None
        job.lease_token = job.lease_until = None
    purge_pretrained(ResearchQueue(sessions(request), config(request)))
    return {"deleted": True}


@router.get("/status", response_model=ResearchStatus)
def status(request: Request, user: CurrentUser) -> ResearchStatus:
    settings = config(request)
    with sessions(request)() as session:
        allowed = settings.research_mode and authorized(session, user.id)
    provider = catalog(settings).status("comboloss")
    deployment = settings.api_environment in {"staging", "production"}
    return ResearchStatus(
        enabled=settings.research_mode,
        authorized=allowed,
        synthetic_available=False,
        providers=[
            ProviderView(
                slug="comboloss",
                display_name="ComboLoss / SEResNeXt50",
                available=provider.available and not deployment,
                reason="deployment_unapproved" if deployment else provider.reason,
            )
        ],
    )
