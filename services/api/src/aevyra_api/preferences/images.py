"""Bounded decoding. Only metadata-free JPEG derivatives enter private storage."""

import base64
import binascii
import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from aevyra_api.commercial.state import DomainError

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = 6 * 1024 * 1024
CONSENT_VERSION = "adult-authorized-v1"


@dataclass(frozen=True)
class DecodedImage:
    image: bytes
    thumbnail: bytes
    original_hash: str
    content_hash: str
    width: int
    height: int


def decode_image(encoded: str) -> DecodedImage:
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise DomainError("Invalid image encoding", 422) from None
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise DomainError("Image exceeds 4 MiB limit", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload), formats=["JPEG", "PNG"]) as source:
                if (
                    source.width > 4096
                    or source.height > 4096
                    or source.width * source.height > 16_000_000
                    or getattr(source, "n_frames", 1) != 1
                ):
                    raise DomainError(
                        "Use a single JPEG/PNG image up to 4096px and 16 megapixels", 422
                    )
                source.load()
                oriented = ImageOps.exif_transpose(source)
                normalized = oriented.convert("RGB")
                normalized.thumbnail((2048, 2048))
                normalized.info.clear()
                content_hash = hashlib.sha256(
                    f"{normalized.width}x{normalized.height}:".encode() + normalized.tobytes()
                ).hexdigest()
                full = BytesIO()
                normalized.save(full, format="JPEG", quality=90)
                normalized.thumbnail((256, 256))
                thumb = BytesIO()
                normalized.save(thumb, format="JPEG", quality=85)
                with Image.open(BytesIO(full.getvalue())) as stored:
                    return DecodedImage(
                        full.getvalue(),
                        thumb.getvalue(),
                        hashlib.sha256(payload).hexdigest(),
                        content_hash,
                        stored.width,
                        stored.height,
                    )
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise DomainError("Invalid or unsupported JPEG/PNG image", 422) from None
