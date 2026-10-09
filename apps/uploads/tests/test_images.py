import io

import pytest
from PIL import Image

from apps.uploads import images
from apps.uploads.tests.helpers import content_type_of, image_bytes


def open_webp(data):
    image = Image.open(io.BytesIO(data))
    assert image.format == "WEBP"
    return image


# --- recognising the real type ---


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_each_allowed_type_is_recognised_from_its_bytes(fmt):
    assert images.sniff(image_bytes(fmt)) == content_type_of(fmt)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF89a....",
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"%PDF-1.7",
        b"RIFF" + b"\0" * 20,
    ],
)
def test_other_content_is_not_recognised(data):
    assert images.sniff(data) is None


# --- producing clean copies ---


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_every_input_type_becomes_webp_variants(fmt):
    out = images.process(image_bytes(fmt, (800, 600)), content_type_of(fmt))
    assert open_webp(out.large).size == (800, 600)
    assert open_webp(out.thumb).size == (320, 240)
    assert (out.width, out.height) == (800, 600)


def test_small_images_are_never_enlarged():
    out = images.process(image_bytes("PNG", (100, 80)), "image/png")
    assert open_webp(out.large).size == (100, 80)
    assert open_webp(out.thumb).size == (100, 80)


def test_big_images_are_scaled_down_keeping_their_shape(settings):
    out = images.process(image_bytes("JPEG", (3000, 2000)), "image/jpeg")
    width, height = open_webp(out.large).size
    assert max(width, height) == settings.IMAGE_LARGE_SIDE
    assert abs(width / height - 1.5) < 0.01
    assert max(open_webp(out.thumb).size) == settings.IMAGE_THUMB_SIDE


def test_metadata_is_stripped():
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    exif[0x8825] = {1: "N", 2: (6.0, 27.0, 0.0)}  # GPS block
    out = images.process(image_bytes("JPEG", (200, 100), exif=exif.tobytes()), "image/jpeg")
    for variant in (out.large, out.thumb):
        assert b"SecretCameraMaker" not in variant
        assert not open_webp(variant).getexif()


def test_the_orientation_flag_is_applied_not_just_dropped():
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 degrees"
    out = images.process(image_bytes("JPEG", (40, 20), exif=exif.tobytes()), "image/jpeg")
    assert (out.width, out.height) == (20, 40)
    assert open_webp(out.large).size == (20, 40)


def test_transparency_is_kept():
    source = Image.new("RGBA", (50, 50), (255, 0, 0, 0))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")
    out = images.process(buffer.getvalue(), "image/png")
    result = open_webp(out.large).convert("RGBA")
    assert result.getpixel((10, 10))[3] == 0


def test_palette_images_with_transparency_work():
    source = Image.new("P", (30, 30), 0)
    buffer = io.BytesIO()
    source.save(buffer, format="PNG", transparency=0)
    assert images.process(buffer.getvalue(), "image/png").width == 30


def test_data_hidden_after_the_image_does_not_survive():
    hidden = b"<script>alert('hi')</script>PK\x03\x04MZ-HIDDEN-PAYLOAD"
    out = images.process(image_bytes("JPEG") + hidden, "image/jpeg")
    for variant in (out.large, out.thumb):
        assert b"HIDDEN-PAYLOAD" not in variant and b"<script>" not in variant


# --- refusing what is not what it claims ---


def code_of(data, declared):
    with pytest.raises(images.ImageRejected) as caught:
        images.process(data, declared)
    return caught.value.code


def test_a_file_whose_bytes_disagree_with_its_declared_type_is_refused():
    assert code_of(image_bytes("PNG"), "image/jpeg") == "type_mismatch"
    assert code_of(image_bytes("WEBP"), "image/png") == "type_mismatch"
    assert code_of(b"", "image/png") == "type_mismatch"
    assert code_of(b"GIF89a" + b"\0" * 40, "image/png") == "type_mismatch"


def test_a_file_with_the_right_signature_but_no_image_inside_is_refused():
    assert code_of(b"\x89PNG\r\n\x1a\n" + b"not really a png" * 10, "image/png") == "not_an_image"
    assert code_of(b"\xff\xd8\xff" + b"\x00" * 50, "image/jpeg") == "not_an_image"


def test_a_truncated_image_is_refused():
    valid = image_bytes("PNG", (200, 200))
    assert code_of(valid[: len(valid) // 3], "image/png") == "not_an_image"


def test_images_with_absurd_dimensions_are_refused(settings):
    settings.IMAGE_MAX_SIDE = 50
    assert code_of(image_bytes("PNG", (100, 20)), "image/png") == "too_large_dimensions"


def test_decompression_bombs_are_refused(settings):
    settings.IMAGE_MAX_PIXELS = 1000
    assert code_of(image_bytes("PNG", (100, 100)), "image/png") == "too_large_dimensions"
