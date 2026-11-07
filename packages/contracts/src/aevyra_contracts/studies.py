"""Study collection contracts. Consent is explicit; native labels are always 1–7."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudyCreate(Strict):
    idempotency_key: UUID
    title: str = Field(min_length=3, max_length=120)
    partition: Literal["development", "holdout"] = "development"
    custodian_public_id: str | None = Field(default=None, max_length=40)
    fixture_only: bool = True
    retention_days: int = Field(default=30, ge=1, le=90)


class ConsentPublish(Strict):
    idempotency_key: UUID
    text_en: str = Field(min_length=100, max_length=12000)
    text_zh: str = Field(min_length=50, max_length=12000)
    contact_en: str = Field(min_length=3, max_length=300)
    contact_zh: str = Field(min_length=3, max_length=300)
    rights_reference: str = Field(min_length=3, max_length=200)


class StudyAction(Strict):
    idempotency_key: UUID
    action: Literal["open", "pause", "close", "rotate_invite", "seal"]
    reason: str = Field(min_length=3, max_length=200)


class InviteResolve(Strict):
    invite_code: str = Field(min_length=32, max_length=120)


class StudyJoin(InviteResolve):
    consent_id: UUID
    consent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    role: Literal["contributor", "rater", "custodian"]
    adult_confirmed: Literal[True]
    voluntary: Literal[True]
    understood: Literal[True]
    research_permission: Literal[True]
    fixture_confirmed: bool = False


class MemberReview(Strict):
    idempotency_key: UUID
    approved: bool
    verification_reference: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,79}$")


class PhotoUpload(Strict):
    idempotency_key: UUID
    self_portrait: Literal[True]
    adult_confirmed: Literal[True]
    rights_confirmed: Literal[True]
    fixture_confirmed: bool = False
    pose: Literal["frontal", "left", "right", "other"]
    lighting: Literal["diffuse", "side", "low", "other"]


class PhotoReview(Strict):
    idempotency_key: UUID
    approved: bool
    reason: str = Field(min_length=3, max_length=200)


class RatingSubmit(Strict):
    score: int | None = Field(default=None, ge=1, le=7, strict=True)
    skip: bool = False


class StudyCommand(Strict):
    idempotency_key: UUID


class ExportCreate(StudyCommand):
    include_adjusted: bool = Field(default=False, strict=True)


class ConsentView(Strict):
    id: UUID
    version: int
    sha256: str
    text_en: str
    text_zh: str
    contact_en: str
    contact_zh: str
    rights_reference: str
    created_at: datetime


class PhotoView(Strict):
    id: UUID
    review: str
    pose: str
    lighting: str
    rating_count: int
    created_at: datetime


class MemberView(Strict):
    id: UUID
    role: str
    approved: bool
    active: bool
    verification_reference: str | None = None


class StudyView(Strict):
    id: UUID
    title: str
    partition: Literal["development", "holdout"]
    status: str
    fixture_only: bool
    retention_days: int
    can_manage: bool
    can_administer: bool
    consent: ConsentView | None
    memberships: list[MemberView]
    members: list[MemberView]
    photos: list[PhotoView]
    seal_sha256: str | None
    revision: int
    photo_count: int
    rating_count: int


class AssignmentView(Strict):
    id: UUID
    expires_at: datetime
    not_before: datetime


class ExportView(Strict):
    id: UUID
    status: str
    sha256: str
    images: int
    subjects: int
    expires_at: datetime
