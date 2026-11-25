"""Gemini API adapter for the photo check: photo technique plus constructive appearance
feedback and an optional photo-only roast (AGENTS.md, owner decision 2026-11-25).

Provider-neutral boundary: the service depends on ``PhotoQualityProvider`` only. This
adapter calls the Gemini Developer API (Standard paid tier) over HTTPS with the standard
library, requests strict JSON and validates it. Request bodies, photos, keys and response
text are never logged.
"""

import base64
import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from aevyra_contracts.photo_check import ARCHETYPES, CRITERIA, Language, RoastLevel
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ENGINE = "gemini-photo-check"
PROMPT_VERSION = "photo-appearance-v1"
# Fixed so repeated checks of the same photo agree as far as the provider allows.
SEED = 20261125
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "zh-CN": "Simplified Chinese"}
REFUSALS = ["no_person", "multiple_people", "not_a_photo", "appears_under_18", "explicit"]
ModelRefusal = Literal[
    "no_person", "multiple_people", "not_a_photo", "appears_under_18", "explicit"
]
APPEARANCE_FIELDS = ("appearance_strengths", "appearance_flattering", "appearance_tips")
MAX_TIP_CHARS = 120
# Gemini API keys are printable ASCII tokens: classic "AIza..." keys (39 characters) and the
# newer "AQ." auth keys (dotted, ~53 characters). HTTP header values must be plain ASCII;
# anything else (curly quotes, zero-width spaces, "…" from copy-paste) would raise
# UnicodeEncodeError inside http.client, or be sent and rejected by Google.
API_KEY_PATTERN = re.compile(r"[A-Za-z0-9._~+/=-]{20,256}")


def api_key_problem(key: str) -> str | None:
    """Fixed-vocabulary reason a key cannot be sent, safe to log; None when usable."""
    if API_KEY_PATTERN.fullmatch(key):
        return None
    if any(ord(char) > 127 for char in key):
        return "non_ascii_character"
    if any(char.isspace() for char in key):
        return "whitespace"
    if any(char in "\"'`" for char in key):
        return "quote_character"
    if not 20 <= len(key) <= 256:
        return "unexpected_length"
    return "unexpected_character"


SYSTEM_PROMPT = """You give friendly, constructive feedback on profile photos. Each photo was
uploaded by an adult who confirmed it shows themselves and asked for this feedback.
Images are numbered from 0 in the order given. For each image:

1. Photo technique. Integers 1-10:
- lighting: even, soft light on the face; no harsh shadows, glare or blown highlights
- sharpness: the eyes are in focus; no motion blur, heavy noise or compression
- framing: head and shoulders well placed, nothing awkwardly cut off, sensible distance and angle
- expression: looks relaxed and natural, eyes open
- eye_contact: looking towards the camera
- background: tidy and not distracting; the person stands out from it
tips: at most 2 practical tips for taking a better photo.

2. Appearance. Kind and constructive only.
- appearance_strengths: up to 3 genuine strengths: facial features, expression, hair, grooming
  or styling.
- appearance_flattering: up to 3 notes on what flatters this person in photos: angles, light,
  colours, framing, clothing or hairstyle.
- appearance_tips: up to 3 practical, kind tips on styling, hair, grooming, posing or which
  photos to choose.
- band: overall impression in photos, an integer 1-4: 1 = this photo does not show them at
  their best, 2 = average, 3 = attractive, 4 = striking.
Never call anything a flaw, defect or imperfection, or use any similar word. Never suggest
cosmetic surgery, fillers, injections, medical treatment, medication or diets. Never mention
race, ethnicity, skin colour, body weight, body size or age.

3. {roast}

Write every text field in {language}, each under 90 characters.
When no person is clearly visible (no_person), more than one person is prominent
(multiple_people), it is not a photograph, for example a drawing or screenshot
(not_a_photo), the person might be under 18 (appears_under_18), or there is nudity or
sexual content (explicit): set refusal_reason, leave every score and band null and every
list empty, and set vibe to null. Otherwise refusal_reason is null.
Return only JSON that matches the schema."""

ROAST_OFF = "Roast: off. Leave roast_lines empty and set vibe to null."
ROAST_TONE = {
    "gentle": "Keep it light and warm, like a friend teasing.",
    "spicy": (
        "Make it sharper and wittier, but keep the same targets; never meaner about the person."
    ),
}
ROAST_ON = """Roast ({level}): up to 2 short, funny roast_lines that tease only the photo and the
situation: lighting, camera angle, blur, background, timing, pose or styling choices. {tone}
Never joke about the body, skin, acne, weight, facial features, age, race, gender,
disability or health. Never compare the person to a real or famous person, and never say who
they look like. If no joke fits these limits, leave roast_lines empty.
vibe: the one style from the allowed list that best matches the photo's overall look. It is
a style, not a person."""


def response_schema() -> dict[str, object]:
    score = {"type": "INTEGER", "nullable": True}
    texts = {"type": "ARRAY", "items": {"type": "STRING"}}
    order = [
        "index",
        "refusal_reason",
        *CRITERIA,
        "tips",
        *APPEARANCE_FIELDS,
        "band",
        "roast_lines",
        "vibe",
    ]
    photo = {
        "type": "OBJECT",
        "properties": {
            "index": {"type": "INTEGER"},
            "refusal_reason": {"type": "STRING", "enum": REFUSALS, "nullable": True},
            **{name: score for name in CRITERIA},
            "tips": texts,
            **{name: texts for name in APPEARANCE_FIELDS},
            "band": {"type": "INTEGER", "nullable": True},
            "roast_lines": texts,
            "vibe": {"type": "STRING", "enum": list(ARCHETYPES), "nullable": True},
        },
        "required": order,
        "propertyOrdering": order,
    }
    return {
        "type": "OBJECT",
        "properties": {"photos": {"type": "ARRAY", "items": photo}},
        "required": ["photos"],
    }


class ProviderError(Exception):
    """Expected provider failure; ``reason`` is a fixed vocabulary safe to log."""

    def __init__(
        self,
        reason: Literal["provider_unavailable", "provider_rejected", "invalid_response", "blocked"],
        usage: "Usage | None" = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.usage = usage
        self.status_code = status_code


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    # Billed output: response plus thinking tokens.
    output_tokens: int


class ModelPhoto(BaseModel):
    model_config = ConfigDict(extra="ignore")
    index: int = Field(ge=0)
    refusal_reason: ModelRefusal | None
    lighting: int | None = Field(ge=1, le=10)
    sharpness: int | None = Field(ge=1, le=10)
    framing: int | None = Field(ge=1, le=10)
    expression: int | None = Field(ge=1, le=10)
    eye_contact: int | None = Field(ge=1, le=10)
    background: int | None = Field(ge=1, le=10)
    tips: list[str] = Field(max_length=4)
    appearance_strengths: list[str] = Field(default_factory=list, max_length=5)
    appearance_flattering: list[str] = Field(default_factory=list, max_length=5)
    appearance_tips: list[str] = Field(default_factory=list, max_length=5)
    band: int | None = Field(default=None, ge=1, le=4)
    roast_lines: list[str] = Field(default_factory=list, max_length=4)
    # Any other string fails validation, so a vibe can never be a person's name.
    vibe: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> "ModelPhoto":
        scores = [getattr(self, name) for name in CRITERIA]
        if self.refusal_reason is None and (
            any(value is None for value in scores) or self.band is None
        ):
            raise ValueError("Usable photo without every score and a band")
        if self.vibe is not None and self.vibe not in ARCHETYPES:
            raise ValueError("Vibe outside the archetype list")
        return self


class ModelAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    photos: list[ModelPhoto]


@dataclass(frozen=True)
class Assessment:
    photos: list[ModelPhoto]
    usage: Usage


class TokenBudget(Protocol):
    def max_output_tokens(self, photos: int) -> int: ...

    def estimated_input_tokens(self, photos: int) -> int: ...


class PhotoQualityProvider(TokenBudget, Protocol):
    model: str

    def assess(
        self, images: Sequence[bytes], language: Language, roast: RoastLevel = "off"
    ) -> Assessment: ...


Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, bytes]]


def urllib_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as error:
        return int(error.code), b""
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("provider_unavailable") from None


class TokenEstimates:
    """Request-size bounds used for cost reservations; needs no key."""

    def max_output_tokens(self, photos: int) -> int:
        # Technique, appearance and roast text per photo, kept short by the prompt.
        return 300 + 450 * photos

    def estimated_input_tokens(self, photos: int) -> int:
        # Instructions and schema, plus 560 tokens per photo at medium resolution, rounded up.
        return 1400 + 700 * photos


ESTIMATOR = TokenEstimates()


class GeminiPhotoQuality(TokenEstimates):
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        thinking_level: str = "minimal",
        timeout: float = 30.0,
        transport: Transport = urllib_transport,
    ) -> None:
        problem = api_key_problem(api_key)
        if problem is not None:
            raise ValueError(f"Gemini API key rejected: {problem}")
        self._api_key = api_key
        self.model = model
        self._thinking_level = thinking_level
        self._timeout = timeout
        self._transport = transport

    def request_body(
        self, images: Sequence[bytes], language: Language, roast: RoastLevel = "off"
    ) -> dict[str, object]:
        parts: list[dict[str, object]] = [
            {"text": f"{len(images)} photo(s) follow, numbered from 0."}
        ]
        parts.extend(
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}}
            for image in images
        )
        config: dict[str, object] = {
            "temperature": 0,
            "seed": SEED,
            "responseMimeType": "application/json",
            "responseSchema": response_schema(),
            "maxOutputTokens": self.max_output_tokens(len(images)),
            "mediaResolution": "MEDIA_RESOLUTION_MEDIUM",
        }
        if self._thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
        return {
            "systemInstruction": {
                "parts": [
                    {
                        "text": SYSTEM_PROMPT.format(
                            language=LANGUAGE_NAMES[language],
                            roast=(
                                ROAST_OFF
                                if roast == "off"
                                else ROAST_ON.format(level=roast, tone=ROAST_TONE[roast])
                            ),
                        )
                    }
                ]
            },
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": config,
        }

    def assess(
        self, images: Sequence[bytes], language: Language, roast: RoastLevel = "off"
    ) -> Assessment:
        body = json.dumps(self.request_body(images, language, roast)).encode()
        status, payload = self._transport(
            ENDPOINT.format(model=self.model),
            {"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            body,
            self._timeout,
        )
        if status == 429 or status >= 500:
            raise ProviderError("provider_unavailable", status_code=status)
        if status != 200:
            raise ProviderError("provider_rejected", status_code=status)
        return parse_response(payload, len(images))


def parse_response(payload: bytes, photos: int) -> Assessment:
    try:
        data = json.loads(payload)
        metadata = data.get("usageMetadata", {})
        usage = Usage(
            int(metadata.get("promptTokenCount", 0)),
            int(metadata.get("candidatesTokenCount", 0))
            + int(metadata.get("thoughtsTokenCount", 0)),
        )
    except (ValueError, TypeError, AttributeError):
        raise ProviderError("invalid_response") from None
    if data.get("promptFeedback", {}).get("blockReason"):
        raise ProviderError("blocked", usage)
    try:
        candidate = data["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            raise ProviderError(
                "blocked" if candidate.get("finishReason") == "SAFETY" else "invalid_response",
                usage,
            )
        text = "".join(
            part.get("text", "")
            for part in candidate["content"]["parts"]
            if not part.get("thought")
        )
        assessment = ModelAssessment.model_validate_json(text)
    except ProviderError:
        raise
    except (KeyError, IndexError, TypeError, AttributeError, ValidationError):
        raise ProviderError("invalid_response", usage) from None
    if sorted(photo.index for photo in assessment.photos) != list(range(photos)):
        raise ProviderError("invalid_response", usage)
    return Assessment(sorted(assessment.photos, key=lambda photo: photo.index), usage)
