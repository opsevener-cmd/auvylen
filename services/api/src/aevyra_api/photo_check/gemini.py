"""Gemini API adapter for the photo-quality check.

Provider-neutral boundary: the service depends on ``PhotoQualityProvider`` only. This
adapter calls the Gemini Developer API (Standard paid tier) over HTTPS with the standard
library, requests strict JSON and validates it. Request bodies, photos, keys and response
text are never logged.
"""

import base64
import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from aevyra_contracts.photo_check import CRITERIA, Language, RefusalReason
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

ENGINE = "gemini-photo-quality"
PROMPT_VERSION = "photo-quality-v1"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "zh-CN": "Simplified Chinese"}
REFUSALS = ["no_person", "multiple_people", "not_a_photo", "appears_under_18", "explicit"]
MAX_TIP_CHARS = 120

SYSTEM_PROMPT = """You review profile photos for photographic technique only.
Images are numbered from 0 in the order given. For each image return integers 1-10:
- lighting: even, soft light on the face; no harsh shadows, glare or blown highlights
- sharpness: the eyes are in focus; no motion blur, heavy noise or compression
- framing: head and shoulders well placed, nothing awkwardly cut off, sensible distance and angle
- expression: looks relaxed and natural, eyes open
- eye_contact: looking towards the camera
- background: tidy and not distracting; the person stands out from it
Judge the photo, never the person. Never comment on attractiveness, face or body shape,
skin, weight, age, ethnicity or any other physical trait.
Give at most two short, practical tips per photo about taking a better photo
(under 90 characters each), written in {language}.
Set refusal_reason, with every score null and no tips, when: no person is clearly visible
(no_person); more than one person is prominent (multiple_people); it is not a photograph,
for example a drawing or screenshot (not_a_photo); the person might be under 18
(appears_under_18); there is nudity or sexual content (explicit). Otherwise refusal_reason
is null. Return only JSON that matches the schema."""


def response_schema() -> dict[str, object]:
    score = {"type": "INTEGER", "nullable": True}
    photo = {
        "type": "OBJECT",
        "properties": {
            "index": {"type": "INTEGER"},
            "refusal_reason": {"type": "STRING", "enum": REFUSALS, "nullable": True},
            **{name: score for name in CRITERIA},
            "tips": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["index", "refusal_reason", *CRITERIA, "tips"],
        "propertyOrdering": ["index", "refusal_reason", *CRITERIA, "tips"],
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
    refusal_reason: RefusalReason | None
    lighting: int | None = Field(ge=1, le=10)
    sharpness: int | None = Field(ge=1, le=10)
    framing: int | None = Field(ge=1, le=10)
    expression: int | None = Field(ge=1, le=10)
    eye_contact: int | None = Field(ge=1, le=10)
    background: int | None = Field(ge=1, le=10)
    tips: list[str] = Field(max_length=4)

    @model_validator(mode="after")
    def consistent(self) -> "ModelPhoto":
        scores = [getattr(self, name) for name in CRITERIA]
        if self.refusal_reason is None and any(value is None for value in scores):
            raise ValueError("Usable photo without every score")
        return self


class ModelAssessment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    photos: list[ModelPhoto]


@dataclass(frozen=True)
class Assessment:
    photos: list[ModelPhoto]
    usage: Usage


class PhotoQualityProvider(Protocol):
    model: str

    def max_output_tokens(self, photos: int) -> int: ...

    def estimated_input_tokens(self, photos: int) -> int: ...

    def assess(self, images: Sequence[bytes], language: Language) -> Assessment: ...


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


class GeminiPhotoQuality:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        thinking_level: str = "minimal",
        timeout: float = 30.0,
        transport: Transport = urllib_transport,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._thinking_level = thinking_level
        self._timeout = timeout
        self._transport = transport

    def max_output_tokens(self, photos: int) -> int:
        return 200 + 220 * photos

    def estimated_input_tokens(self, photos: int) -> int:
        # Instructions and schema, plus 560 tokens per photo at medium resolution, rounded up.
        return 900 + 700 * photos

    def request_body(self, images: Sequence[bytes], language: Language) -> dict[str, object]:
        parts: list[dict[str, object]] = [
            {"text": f"{len(images)} photo(s) follow, numbered from 0."}
        ]
        parts.extend(
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}}
            for image in images
        )
        config: dict[str, object] = {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": response_schema(),
            "maxOutputTokens": self.max_output_tokens(len(images)),
            "mediaResolution": "MEDIA_RESOLUTION_MEDIUM",
        }
        if self._thinking_level:
            config["thinkingConfig"] = {"thinkingLevel": self._thinking_level}
        return {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT.format(language=LANGUAGE_NAMES[language])}]
            },
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": config,
        }

    def assess(self, images: Sequence[bytes], language: Language) -> Assessment:
        body = json.dumps(self.request_body(images, language)).encode()
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
