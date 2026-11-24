"""Free photo-quality check: photo technique only, never attractiveness or physical traits."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONSENT_VERSION = "gemini-paid-v1"
MAX_PHOTOS = 5
CRITERIA = ("lighting", "sharpness", "framing", "expression", "eye_contact", "background")

Availability = Literal["ready", "disabled", "not_configured", "paid_tier_unconfirmed", "paused"]
RefusalReason = Literal[
    "no_person", "multiple_people", "not_a_photo", "appears_under_18", "explicit"
]
Language = Literal["en", "zh-CN"]
Score = Annotated[int, Field(ge=1, le=10)]


class PhotoCheckStatus(BaseModel):
    available: bool
    reason: Availability
    consent_version: str
    consent_required: bool
    used_today: int
    daily_limit: int
    max_photos: int


class PhotoCheckConsentRequest(BaseModel):
    """The user's own statements. Age is never estimated to admit anyone."""

    model_config = ConfigDict(extra="forbid")
    consent_version: Literal["gemini-paid-v1"]
    adult_confirmed: Literal[True]
    processing_accepted: Literal[True]


class PhotoCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Base64 JPEG/PNG; the browser downsizes before upload and the server re-checks.
    photos: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=MAX_PHOTOS)
    language: Language = "en"


class PhotoScores(BaseModel):
    lighting: Score
    sharpness: Score
    framing: Score
    expression: Score
    eye_contact: Score
    background: Score


class PhotoCheckPhoto(BaseModel):
    index: int
    rank: int | None
    usable: bool
    refusal_reason: RefusalReason | None
    scores: PhotoScores | None
    # Mean of the six photo-technique criteria (1-10), and the same rounded for display.
    raw_score: float | None
    display_score: float | None
    tips: list[str]


class PhotoCheckResult(BaseModel):
    id: UUID
    photos: list[PhotoCheckPhoto]
    engine: str
    model: str
    prompt_version: str
    created_at: datetime
    used_today: int
    daily_limit: int
