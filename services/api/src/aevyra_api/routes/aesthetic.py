from urllib.parse import unquote
from uuid import UUID

from aevyra_contracts.aesthetic import (
    AestheticAnalysisView,
    AestheticStatus,
    AestheticUploadMetadata,
)
from aevyra_contracts.commercial import EmptyRequest
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aevyra_api.aesthetic.service import AestheticService
from aevyra_api.commercial.state import DomainError
from aevyra_api.preferences.images import MAX_UPLOAD_BYTES, decode_image_bytes
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions
from aevyra_api.routes.preferences import upload_slots

router = APIRouter(prefix="/api/v1/research/aesthetic", tags=["aesthetic analysis"])


def service(request: Request) -> AestheticService:
    return AestheticService(sessions(request), config(request))


@router.get("/status", response_model=AestheticStatus)
def status(request: Request, user: CurrentUser) -> AestheticStatus:
    return service(request).status(user.id)


@router.post(
    "/analyses",
    response_model=AestheticAnalysisView,
    status_code=202,
    dependencies=[Depends(csrf)],
)
async def submit(request: Request, user: CurrentUser) -> AestheticAnalysisView:
    data = service(request)
    # Authorize and confirm a validated model before reading any untrusted image bytes.
    await run_in_threadpool(data.check_submit, user.id)
    await run_in_threadpool(rate, request, "analysis", 30, user.public_user_id)
    if request.headers.get("content-type") not in {"image/jpeg", "image/png"}:
        raise DomainError("Upload a JPEG or PNG photograph", 415)
    header = request.headers.get("x-upload-metadata", "")
    if len(header) > 1024:
        raise DomainError("Invalid upload metadata", 422)
    try:
        metadata = AestheticUploadMetadata.model_validate_json(unquote(header, errors="strict"))
    except (ValidationError, UnicodeError):
        raise DomainError("Confirm adult, single-subject and authorization consent", 422) from None
    if not upload_slots.acquire(blocking=False):
        raise DomainError("Image processing busy; retry shortly", 429)
    try:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_UPLOAD_BYTES:
                raise DomainError("Upload request too large", 413)
            payload.extend(chunk)
        decoded = await run_in_threadpool(decode_image_bytes, bytes(payload))
        return await run_in_threadpool(data.submit, user.id, metadata, decoded)
    finally:
        upload_slots.release()


@router.get("/analyses", response_model=list[AestheticAnalysisView])
def analyses(request: Request, user: CurrentUser) -> list[AestheticAnalysisView]:
    return service(request).list(user.id)


@router.get("/analyses/{analysis_id}", response_model=AestheticAnalysisView)
def analysis(analysis_id: UUID, request: Request, user: CurrentUser) -> AestheticAnalysisView:
    return service(request).get(user.id, analysis_id)


@router.post("/analyses/{analysis_id}/delete", dependencies=[Depends(csrf)])
def delete(
    analysis_id: UUID, body: EmptyRequest, request: Request, user: CurrentUser
) -> dict[str, bool]:
    service(request).delete(user.id, analysis_id)
    return {"deleted": True}
