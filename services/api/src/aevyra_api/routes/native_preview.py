"""Private Owner research namespace, separate from consumer analysis."""

from urllib.parse import unquote
from uuid import UUID

from aevyra_contracts.aesthetic import AestheticUploadMetadata
from aevyra_contracts.commercial import EmptyRequest
from aevyra_contracts.research import ResearchJobView
from fastapi import APIRouter, Depends, Request
from pydantic import JsonValue, ValidationError
from starlette.concurrency import run_in_threadpool

from aevyra_api.accounts import COOKIE
from aevyra_api.commercial.state import DomainError
from aevyra_api.preferences.images import MAX_UPLOAD_BYTES
from aevyra_api.research.native_preview import NativePreview, canonical
from aevyra_api.routes.accounts import config, csrf, rate, sessions
from aevyra_api.routes.owner import Owner
from aevyra_api.routes.preferences import upload_slots

router = APIRouter(prefix="/api/v1/research/native-preview", tags=["Owner laboratory preview"])


def service(request: Request) -> NativePreview:
    return NativePreview(sessions(request), config(request))


@router.get("/status")
def status(request: Request, user: Owner) -> dict[str, JsonValue]:
    return service(request).status(user.id)


@router.post("/jobs", response_model=ResearchJobView, status_code=202, dependencies=[Depends(csrf)])
async def submit(request: Request, user: Owner) -> ResearchJobView:
    data = service(request)
    token = request.cookies.get(COOKIE, "")
    await run_in_threadpool(data.check_submit, user.id, token)
    await run_in_threadpool(rate, request, "analysis", 30, user.public_user_id)
    if request.headers.get("content-type") not in {"image/jpeg", "image/png"}:
        raise DomainError("Upload a JPEG or PNG photograph", 415)
    header = request.headers.get("x-upload-metadata", "")
    try:
        if len(header) > 1024:
            raise ValueError("Metadata too long")
        meta = AestheticUploadMetadata.model_validate_json(unquote(header, errors="strict"))
    except (ValidationError, UnicodeError, ValueError):
        raise DomainError("Confirm adult, single-subject and authorization consent", 422) from None
    if not upload_slots.acquire(blocking=False):
        raise DomainError("Image processing busy; retry shortly", 429)
    try:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_UPLOAD_BYTES:
                raise DomainError("Upload request too large", 413)
            payload.extend(chunk)
        image = await run_in_threadpool(canonical, bytes(payload))
        return await run_in_threadpool(data.submit, user.id, token, meta, image)
    finally:
        upload_slots.release()


@router.get("/jobs/{job_id}", response_model=ResearchJobView)
def result(job_id: UUID, request: Request, user: Owner) -> ResearchJobView:
    return service(request).get(user.id, job_id)


@router.post("/jobs/{job_id}/delete", dependencies=[Depends(csrf)])
def delete(job_id: UUID, body: EmptyRequest, request: Request, user: Owner) -> dict[str, bool]:
    service(request).delete(user.id, job_id)
    return {"deleted": True}
