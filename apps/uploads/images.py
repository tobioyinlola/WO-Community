"""Checking and re-encoding images. Pure functions: bytes in, bytes out.

Nothing a client sends survives into the stored file. The image is decoded and
written again from its pixels, which drops metadata, embedded scripts and any
data hidden after the image (polyglot files).
"""

import io
from dataclasses import dataclass

from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),  # plus "WEBP" at byte 8, checked in sniff()
}
FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


class ImageRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProcessedImage:
    large: bytes
    thumb: bytes
    width: int
    height: int


def sniff(data: bytes) -> str | None:
    """The content type the bytes really are, from their first bytes."""
    for content_type, prefixes in SIGNATURES.items():
        if any(data.startswith(prefix) for prefix in prefixes):
            if content_type == "image/webp" and data[8:12] != b"WEBP":
                continue
            return content_type
    return None


def _encode(image: Image.Image, longest_side: int) -> bytes:
    copy = image.copy()
    copy.thumbnail((longest_side, longest_side), Image.Resampling.LANCZOS)  # never upscales
    out = io.BytesIO()
    copy.save(out, format="WEBP", quality=settings.IMAGE_QUALITY, method=4)
    return out.getvalue()


def process(data: bytes, declared_type: str) -> ProcessedImage:
    """Verify an upload really is the image it claims to be and produce clean variants."""
    if sniff(data) != declared_type:
        raise ImageRejected("type_mismatch")
    Image.MAX_IMAGE_PIXELS = settings.IMAGE_MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != FORMATS[declared_type]:
                raise ImageRejected("type_mismatch")
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if max(width, height) > settings.IMAGE_MAX_SIDE or width < 1 or height < 1:
                raise ImageRejected("too_large_dimensions")
            image.load()
            upright = ImageOps.exif_transpose(image)
            has_alpha = "A" in upright.getbands() or "transparency" in upright.info
            clean = upright.convert("RGBA" if has_alpha else "RGB")
    except Image.DecompressionBombError as exc:
        raise ImageRejected("too_large_dimensions") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageRejected("not_an_image") from exc
    return ProcessedImage(
        large=_encode(clean, settings.IMAGE_LARGE_SIDE),
        thumb=_encode(clean, settings.IMAGE_THUMB_SIDE),
        width=clean.width,
        height=clean.height,
    )
