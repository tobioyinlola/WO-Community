import io

from PIL import Image

CONTENT_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def image_bytes(fmt="PNG", size=(400, 300), color=(200, 30, 30), **save_kwargs) -> bytes:
    """A real, valid image in the given format."""
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt, **save_kwargs)
    return out.getvalue()


def content_type_of(fmt: str) -> str:
    return CONTENT_TYPES[fmt]
