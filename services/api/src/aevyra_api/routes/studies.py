"""Private consent collection API. All mutations retain Origin + CSRF enforcement."""

from urllib.parse import unquote
from uuid import UUID

from aevyra_contracts.studies import (
    AssignmentView,
    ConsentPublish,
    ExportCreate,
    ExportView,
    InviteResolve,
    MemberReview,
    PhotoReview,
    PhotoUpload,
    PhotoView,
    RatingSubmit,
    StudyAction,
    StudyCommand,
    StudyCreate,
    StudyJoin,
    StudyView,
)
from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from aevyra_api.accounts import COOKIE
from aevyra_api.commercial.state import DomainError
from aevyra_api.preferences.images import MAX_UPLOAD_BYTES, decode_image_bytes
from aevyra_api.routes.accounts import CurrentUser, config, csrf, rate, sessions
from aevyra_api.routes.owner import Owner
from aevyra_api.routes.preferences import upload_slots
from aevyra_api.studies.exports import Exports
from aevyra_api.studies.models import ConsentVersion, Receipt, StudyAudit
from aevyra_api.studies.service import Studies

router = APIRouter(prefix="/api/v1/research/studies", tags=["consented research studies"])


def service(request: Request) -> Studies:
    return Studies(sessions(request), config(request))


def token(request: Request) -> str:
    return request.cookies.get(COOKIE, "")


@router.get("/status")
def status(request: Request, user: CurrentUser) -> dict[str, bool]:
    s = config(request)
    return {
        "enabled": s.study_collection_enabled and s.research_mode,
        "real_collection_enabled": s.study_real_collection_enabled,
        "owner": user.role == "owner",
        "consumer_scoring_enabled": False,
    }


@router.get("", response_model=list[StudyView])
def listing(request: Request, user: CurrentUser) -> list[StudyView]:
    return service(request).list_studies(user.id)


@router.post("", status_code=201, dependencies=[Depends(csrf)])
def create(body: StudyCreate, request: Request, user: Owner) -> dict[str, str]:
    rate(request, "study-admin", 30, user.public_user_id)
    return {"id": str(service(request).create(user.id, token(request), body))}


@router.post("/resolve-invite", response_model=StudyView, dependencies=[Depends(csrf)])
def resolve(body: InviteResolve, request: Request, user: CurrentUser) -> StudyView:
    rate(request, "study-invite", 20, user.public_user_id)
    return service(request).resolve(user.id, body.invite_code)


@router.post("/join", dependencies=[Depends(csrf)])
def join(body: StudyJoin, request: Request, user: CurrentUser) -> dict[str, str]:
    rate(request, "study-join", 30, user.public_user_id)
    return {"member_id": str(service(request).join(user.id, body))}


@router.get("/{study_id}", response_model=StudyView)
def detail(study_id: UUID, request: Request, user: CurrentUser) -> StudyView:
    return service(request).get(user.id, study_id)


@router.post("/{study_id}/consent", dependencies=[Depends(csrf)])
def consent(study_id: UUID, body: ConsentPublish, request: Request, user: Owner) -> dict[str, bool]:
    service(request).publish(user.id, study_id, token(request), body)
    return {"saved": True}


@router.post("/{study_id}/action", dependencies=[Depends(csrf)])
def action(
    study_id: UUID, body: StudyAction, request: Request, user: CurrentUser
) -> dict[str, str | None]:
    rate(request, "study-admin", 60, user.public_user_id)
    value = service(request).action(user.id, study_id, token(request), body)
    return {"value": value}


@router.post("/{study_id}/members/{member_id}/review", dependencies=[Depends(csrf)])
def member_review(
    study_id: UUID, member_id: UUID, body: MemberReview, request: Request, user: CurrentUser
) -> dict[str, bool]:
    service(request).review_member(user.id, study_id, member_id, token(request), body)
    return {"saved": True}


@router.post(
    "/{study_id}/photos", response_model=PhotoView, status_code=201, dependencies=[Depends(csrf)]
)
async def upload(study_id: UUID, request: Request, user: CurrentUser) -> PhotoView:
    data = service(request)
    data.enabled()
    await run_in_threadpool(rate, request, "study-upload", 20, user.public_user_id)
    if request.headers.get("content-type") not in {"image/jpeg", "image/png"}:
        raise DomainError("study_image_format", 415)
    header = request.headers.get("x-upload-metadata", "")
    try:
        if len(header) > 2048:
            raise ValueError("Metadata limit")
        meta = PhotoUpload.model_validate_json(unquote(header, errors="strict"))
    except (ValidationError, UnicodeError, ValueError):
        raise DomainError("study_upload_attestation", 422) from None
    # Confirm membership before accepting/decoding untrusted image bytes.
    await run_in_threadpool(data.check_upload, user.id, study_id, meta)
    if not upload_slots.acquire(blocking=False):
        raise DomainError("study_busy", 429)
    try:
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_UPLOAD_BYTES:
                raise DomainError("study_image_size", 413)
            payload.extend(chunk)
        decoded = await run_in_threadpool(decode_image_bytes, bytes(payload))
        return await run_in_threadpool(data.upload, user.id, study_id, meta, decoded)
    finally:
        upload_slots.release()


@router.get("/{study_id}/photos/{photo_id}/content")
def review_content(study_id: UUID, photo_id: UUID, request: Request, user: CurrentUser) -> Response:
    return Response(
        service(request).image(user.id, study_id, photo_id=photo_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{study_id}/photos/{photo_id}/review", dependencies=[Depends(csrf)])
def photo_review(
    study_id: UUID, photo_id: UUID, body: PhotoReview, request: Request, user: CurrentUser
) -> dict[str, bool]:
    data = service(request)
    data.review_photo(user.id, study_id, photo_id, token(request), body)
    return {"saved": True, "cleanup_pending": not body.approved and data.drain(study_id) > 0}


@router.post("/{study_id}/photos/{photo_id}/delete", dependencies=[Depends(csrf)])
def photo_delete(
    study_id: UUID, photo_id: UUID, body: StudyCommand, request: Request, user: CurrentUser
) -> dict[str, bool]:
    data = service(request)
    data.delete_photo(user.id, study_id, photo_id, token(request), body.idempotency_key)
    return {"deleted": True, "cleanup_pending": data.drain(study_id) > 0}


@router.post(
    "/{study_id}/assignments", response_model=AssignmentView | None, dependencies=[Depends(csrf)]
)
def assign(
    study_id: UUID, body: StudyCommand, request: Request, user: CurrentUser
) -> AssignmentView | None:
    rate(request, "study-rating", 120, user.public_user_id)
    return service(request).assignment(user.id, study_id)


@router.get("/{study_id}/assignments/{assignment_id}/content")
def assignment_content(
    study_id: UUID, assignment_id: UUID, request: Request, user: CurrentUser
) -> Response:
    return Response(
        service(request).image(user.id, study_id, assignment_id=assignment_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/{study_id}/assignments/{assignment_id}/view",
    response_model=AssignmentView,
    dependencies=[Depends(csrf)],
)
def viewed(
    study_id: UUID, assignment_id: UUID, body: StudyCommand, request: Request, user: CurrentUser
) -> AssignmentView:
    return service(request).viewed(user.id, study_id, assignment_id)


@router.post("/{study_id}/assignments/{assignment_id}/rating", dependencies=[Depends(csrf)])
def rating(
    study_id: UUID, assignment_id: UUID, body: RatingSubmit, request: Request, user: CurrentUser
) -> dict[str, bool]:
    service(request).save_rating(user.id, study_id, assignment_id, body)
    return {"saved": True}


@router.post("/{study_id}/withdraw", dependencies=[Depends(csrf)])
def withdraw(
    study_id: UUID, body: StudyCommand, request: Request, user: CurrentUser
) -> dict[str, bool]:
    rate(request, "study-withdraw", 30, user.public_user_id)
    data = service(request)
    data.withdraw(user.id, study_id, body.idempotency_key)
    return {"withdrawn": True, "cleanup_pending": data.drain(study_id) > 0}


@router.get("/{study_id}/receipts")
def receipts(study_id: UUID, request: Request, user: CurrentUser) -> list[dict[str, object]]:
    # Receipts/withdrawal remain readable after collection is switched off.
    data = service(request)
    with sessions(request)() as session:
        study = data.study(session, study_id)
        own = data.memberships(session, study, user)
        if not own:
            raise DomainError("study_not_found", 404)
        return [
            {
                "id": str(r.id),
                "role": next(m.role for m in own if m.id == r.member_id),
                "accepted_at": r.created_at.isoformat(),
                "consent": {
                    "study_id": str(study.id),
                    "partition": study.partition,
                    "fixture_only": study.fixture_only,
                    "retention_days": study.retention_days,
                    "version": c.version,
                    **{
                        k: getattr(c, k)
                        for k in (
                            "sha256",
                            "text_en",
                            "text_zh",
                            "contact_en",
                            "contact_zh",
                            "rights_reference",
                        )
                    },
                },
            }
            for r, c in session.execute(
                select(Receipt, ConsentVersion)
                .join(ConsentVersion, Receipt.consent_id == ConsentVersion.id)
                .where(Receipt.member_id.in_([m.id for m in own]))
            )
        ]


@router.get("/{study_id}/quality")
def quality(study_id: UUID, request: Request, user: CurrentUser) -> list[dict[str, object]]:
    return service(request).quality(user.id, study_id)


@router.get("/{study_id}/audit")
def study_audit(study_id: UUID, request: Request, user: CurrentUser) -> list[dict[str, object]]:
    data = service(request)
    data.enabled()
    with sessions(request)() as session:
        study = data.study(session, study_id)
        data.manager(session, study, user)
        return [
            {
                "action": row.action,
                "actor_ref": row.actor_ref,
                "created_at": row.created_at.isoformat(),
                "details": row.details,
            }
            for row in session.scalars(
                select(StudyAudit)
                .where(StudyAudit.study_id == study.id)
                .order_by(StudyAudit.created_at.desc())
                .limit(100)
            )
        ]


@router.post(
    "/{study_id}/exports", response_model=ExportView, status_code=201, dependencies=[Depends(csrf)]
)
def export(study_id: UUID, body: ExportCreate, request: Request, user: Owner) -> ExportView:
    rate(request, "study-export", 10, user.public_user_id)
    return Exports(service(request)).create(
        user.id,
        study_id,
        token(request),
        body.idempotency_key,
        include_adjusted=body.include_adjusted,
    )


@router.get("/{study_id}/exports/{export_id}", response_model=ExportView)
def export_status(study_id: UUID, export_id: UUID, request: Request, user: Owner) -> ExportView:
    return Exports(service(request)).info(user.id, study_id, export_id)


@router.get("/{study_id}/exports/{export_id}/content")
def download(study_id: UUID, export_id: UUID, request: Request, user: Owner) -> Response:
    payload = Exports(service(request)).read(user.id, study_id, export_id)
    return Response(
        payload,
        media_type="application/zip",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="auvylen-development-{export_id}.zip"',
            "X-Content-Type-Options": "nosniff",
        },
    )
