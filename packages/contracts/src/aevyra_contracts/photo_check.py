"""Photo check: photo technique plus constructive appearance feedback (owner decision
2026-11-25, AGENTS.md). Never "flaws", never body or identity comments, never named people."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# v2 covers appearance analysis; everyone who accepted v1 must accept again.
CONSENT_VERSION = "gemini-paid-v2"
MAX_PHOTOS = 5
CRITERIA = ("lighting", "sharpness", "framing", "expression", "eye_contact", "background")
# The model may only choose one of these; the UI renders each in plain EN/ZH copy. A fixed
# list means a vibe line can never name or claim to identify a real person.
ARCHETYPES = (
    "hk_film_lead_90s",
    "indie_band_frontman",
    "old_money_weekend",
    "city_pop_album_cover",
    "film_camera_diary",
    "campus_drama_lead",
    "street_style_snap",
    "art_house_poster",
    "sunday_brunch_regular",
    "startup_keynote",
    "travel_vlogger",
    "late_night_jazz_bar",
)

Availability = Literal["ready", "disabled", "not_configured", "paid_tier_unconfirmed", "paused"]
# Public refusals are neutral: "cannot_analyse" covers more than one person, a possible
# minor and explicit content without saying which.
RefusalReason = Literal["no_person", "not_a_photo", "cannot_analyse"]
Language = Literal["en", "zh-CN"]
RoastLevel = Literal["off", "gentle", "spicy"]
Funding = Literal["free_signup", "free_weekly", "credits", "owner"]
Archetype = Literal[
    "hk_film_lead_90s",
    "indie_band_frontman",
    "old_money_weekend",
    "city_pop_album_cover",
    "film_camera_diary",
    "campus_drama_lead",
    "street_style_snap",
    "art_house_poster",
    "sunday_brunch_regular",
    "startup_keynote",
    "travel_vlogger",
    "late_night_jazz_bar",
]
# 1 What 🫣🤣 · 2 Average 🧐 · 3 Attractive 🥹 · 4 Striking 😘🤩 (labels live in the UI).
Band = Literal[1, 2, 3, 4]
Score = Annotated[int, Field(ge=1, le=10)]
Line = Annotated[str, Field(min_length=1, max_length=200)]


class PhotoCheckStatus(BaseModel):
    available: bool
    reason: Availability
    consent_version: str
    consent_required: bool
    # Free checks usable right now (remaining signup checks plus this week's, if unused).
    free_checks_now: int
    free_signup_remaining: int
    # Next Monday (UTC) when a weekly free check becomes available; None if one is free now.
    next_free_on: date | None
    credit_cost: int
    credit_balance: int
    # Roast mode is offered from the second check on; the first stays friendly.
    roast_available: bool
    max_photos: int


class PhotoCheckConsentRequest(BaseModel):
    """The user's own statements. Age is never estimated to admit anyone."""

    model_config = ConfigDict(extra="forbid")
    consent_version: Literal["gemini-paid-v2"]
    adult_confirmed: Literal[True]
    processing_accepted: Literal[True]


class PhotoCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Base64 JPEG/PNG; the browser downsizes before upload and the server re-checks.
    photos: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=MAX_PHOTOS)
    language: Language = "en"
    # Confirmed on every upload: "This is me and I'm 18+".
    self_and_adult_confirmed: Literal[True]
    roast: RoastLevel = "off"


class PhotoScores(BaseModel):
    lighting: Score
    sharpness: Score
    framing: Score
    expression: Score
    eye_contact: Score
    background: Score


class PhotoAppearance(BaseModel):
    strengths: list[Line] = Field(max_length=3)
    flattering: list[Line] = Field(max_length=3)
    tips: list[Line] = Field(max_length=3)
    # Shown only when the user asks: "AI impression for fun, not an objective rating".
    band: Band


class PhotoRoast(BaseModel):
    lines: list[Line] = Field(max_length=2)
    vibe: Archetype | None


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
    appearance: PhotoAppearance | None = None
    roast: PhotoRoast | None = None


class PhotoCheckResult(BaseModel):
    id: UUID
    photos: list[PhotoCheckPhoto]
    engine: str
    model: str
    prompt_version: str
    created_at: datetime
    funding: Funding
    credits_charged: int
    free_checks_now: int
    next_free_on: date | None
