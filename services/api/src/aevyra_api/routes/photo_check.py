import base64
import binascii
import threading

from aevyra_contracts.photo_check import (
    PhotoCheckConsentRequest,
    PhotoCheckRequest,
    PhotoCheckResult,
    PhotoCheckStatus,
)
from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aevyra_api.commercial.state import DomainError
from aevyra_api.photo_check.service import PhotoCheckService, prepare_photo
from aevyra_api.preferences.images import MAX_REQUEST_BYTES
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions

router = APIRouter(prefix="/api/v1/photo-check", tags=["photo check"])
# Each call holds up to five decoded photos and waits on Gemini for seconds.
provider_slots = threading.BoundedSemaphore(4)


def service(request: Request) -> PhotoCheckService:
    factory = getattr(request.app.state, "photo_check_provider", None)
    if factory is not None:
        return PhotoCheckService(sessions(request), config(request), factory)
    return PhotoCheckService(sessions(request), config(request))


@router.get("/status", response_model=PhotoCheckStatus)
def status(request: Request, user: CurrentUser) -> PhotoCheckStatus:
    return service(request).status(user.id)


@router.post("/consent", dependencies=[Depends(csrf)])
def consent(body: PhotoCheckConsentRequest, request: Request, user: CurrentUser) -> dict[str, bool]:
    service(request).accept_consent(user.id, body)
    return {"accepted": True}


def decode_photos(body: PhotoCheckRequest) -> list[bytes]:
    photos = []
    for encoded in body.photos:
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise DomainError("photo_check_invalid_photos", 422) from None
        try:
            photos.append(prepare_photo(payload))
        except DomainError as error:
            raise DomainError("photo_check_invalid_photos", error.status_code) from None
    return photos


@router.post("/analyses", response_model=PhotoCheckResult, dependencies=[Depends(csrf)])
async def analyze(request: Request, user: CurrentUser) -> PhotoCheckResult:
    data = service(request)
    # Consent and availability are checked before any untrusted photo is read.
    await run_in_threadpool(data.check_submit, user.id)
    await run_in_threadpool(rate, request, "photo-check", 60, user.public_user_id)
    if not provider_slots.acquire(blocking=False):
        raise DomainError("photo_check_busy", 429)
    try:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_REQUEST_BYTES:
                raise DomainError("photo_check_too_large", 413)
            payload.extend(chunk)
        try:
            body = PhotoCheckRequest.model_validate_json(payload)
        except ValidationError as error:
            # Own face and 18+ are confirmed on every upload; say so specifically.
            if any(issue["loc"][:1] == ("self_and_adult_confirmed",) for issue in error.errors()):
                raise DomainError("photo_check_confirmation_required", 422) from None
            raise DomainError("photo_check_invalid_photos", 422) from None
        photos = await run_in_threadpool(decode_photos, body)
        return await run_in_threadpool(data.analyze, user.id, photos, body.language, body.roast)
    finally:
        provider_slots.release()
