import threading
from uuid import UUID

from aevyra_contracts.commercial import EmptyRequest
from aevyra_contracts.preferences import (
    DatasetCreate,
    DatasetDetail,
    DatasetEdit,
    DatasetView,
    ImageEdit,
    ImageUpload,
    ImageView,
    PairInput,
    PairView,
    ProjectCreate,
    ProjectView,
    RatingInput,
)
from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from aevyra_api.commercial.state import DomainError
from aevyra_api.preferences.images import MAX_REQUEST_BYTES, decode_image
from aevyra_api.preferences.service import PreferenceService
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions

router = APIRouter(prefix="/api/v1/research/preferences", tags=["private preference datasets"])
upload_slots = threading.BoundedSemaphore(2)


def service(request: Request) -> PreferenceService:
    return PreferenceService(sessions(request), config(request))


@router.get("/projects", response_model=list[ProjectView])
def projects(request: Request, user: CurrentUser) -> list[ProjectView]:
    return service(request).projects(user.id)


@router.post("/projects", response_model=ProjectView, dependencies=[Depends(csrf)])
def create_project(body: ProjectCreate, request: Request, user: CurrentUser) -> ProjectView:
    return service(request).create_project(user.id, body.name)


@router.get("/datasets", response_model=list[DatasetView])
def datasets(request: Request, user: CurrentUser) -> list[DatasetView]:
    return service(request).datasets(user.id)


@router.post("/datasets", response_model=DatasetView, dependencies=[Depends(csrf)])
def create_dataset(body: DatasetCreate, request: Request, user: CurrentUser) -> DatasetView:
    return service(request).create_dataset(user.id, body)


@router.get("/datasets/{dataset_id}", response_model=DatasetDetail)
def detail(dataset_id: UUID, request: Request, user: CurrentUser) -> DatasetDetail:
    return service(request).detail(user.id, dataset_id)


@router.post(
    "/datasets/{dataset_id}/edit", response_model=DatasetView, dependencies=[Depends(csrf)]
)
def edit_dataset(
    dataset_id: UUID, body: DatasetEdit, request: Request, user: CurrentUser
) -> DatasetView:
    return service(request).edit_dataset(user.id, dataset_id, body)


@router.post(
    "/datasets/{dataset_id}/images", response_model=ImageView, dependencies=[Depends(csrf)]
)
async def upload(dataset_id: UUID, request: Request, user: CurrentUser) -> ImageView:
    data = service(request)
    # Authenticate/authorize before reading an untrusted upload; decode outside the event loop.
    await run_in_threadpool(data.check_upload, user.id, dataset_id)
    await run_in_threadpool(rate, request, "analysis", 120, user.public_user_id)
    if not upload_slots.acquire(blocking=False):
        raise DomainError("Image processing busy; retry shortly", 429)
    try:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_REQUEST_BYTES:
                raise DomainError("Upload request too large", 413)
            payload.extend(chunk)
        try:
            body = ImageUpload.model_validate_json(payload)
        except ValidationError:
            raise DomainError(
                "Invalid upload fields or missing adult/authorization consent", 422
            ) from None
        decoded = await run_in_threadpool(decode_image, body.content_base64)
        return await run_in_threadpool(data.upload, user.id, dataset_id, body, decoded)
    finally:
        upload_slots.release()


@router.get("/datasets/{dataset_id}/images/{image_id}/content")
def content(
    dataset_id: UUID, image_id: UUID, request: Request, user: CurrentUser, thumbnail: bool = False
) -> Response:
    return Response(
        service(request).read(user.id, dataset_id, image_id, thumbnail),
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@router.post(
    "/datasets/{dataset_id}/images/{image_id}/edit",
    response_model=ImageView,
    dependencies=[Depends(csrf)],
)
def edit_image(
    dataset_id: UUID, image_id: UUID, body: ImageEdit, request: Request, user: CurrentUser
) -> ImageView:
    return service(request).edit_image(user.id, dataset_id, image_id, body)


@router.post(
    "/datasets/{dataset_id}/images/{image_id}/rating",
    response_model=ImageView,
    dependencies=[Depends(csrf)],
)
def rating(
    dataset_id: UUID, image_id: UUID, body: RatingInput, request: Request, user: CurrentUser
) -> ImageView:
    return service(request).rate(user.id, dataset_id, image_id, body.score)


@router.post("/datasets/{dataset_id}/pairs", response_model=PairView, dependencies=[Depends(csrf)])
def pair(dataset_id: UUID, body: PairInput, request: Request, user: CurrentUser) -> PairView:
    return service(request).pair(user.id, dataset_id, body)


@router.post("/datasets/{dataset_id}/delete", dependencies=[Depends(csrf)])
def delete_dataset(
    dataset_id: UUID, body: EmptyRequest, request: Request, user: CurrentUser
) -> dict[str, bool]:
    service(request).delete(user.id, dataset_id)
    return {"deleted": True}


@router.post("/datasets/{dataset_id}/images/{image_id}/delete", dependencies=[Depends(csrf)])
def delete_image(
    dataset_id: UUID, image_id: UUID, body: EmptyRequest, request: Request, user: CurrentUser
) -> dict[str, bool]:
    service(request).delete(user.id, dataset_id, image_id)
    return {"deleted": True}
