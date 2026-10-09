import base64
import io
import json

import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from apps.integrations.storage import MEDIA, QUARANTINE, ObjectTooLarge, get_storage
from apps.integrations.storage.fake import FakeStorage, UploadRefused
from apps.integrations.storage.s3 import S3Storage

# --- the fake, which the other tests rely on ---


def test_settings_select_the_fake_storage_in_tests():
    assert isinstance(get_storage(), FakeStorage)


def test_the_fake_enforces_the_form_like_real_storage():
    storage = FakeStorage()
    post = storage.presign_post(
        bucket=QUARANTINE, key="a/b", content_type="image/png", max_size=10, expires_in=60
    )
    FakeStorage.client_upload(post, b"0123456789", "image/png")
    assert storage.head(bucket=QUARANTINE, key="a/b").size == 10
    with pytest.raises(UploadRefused):
        FakeStorage.client_upload(post, b"01234567890", "image/png")
    with pytest.raises(UploadRefused):
        FakeStorage.client_upload(post, b"0123", "image/jpeg")


def test_the_fake_reads_writes_and_deletes():
    storage = FakeStorage()
    storage.write(bucket=MEDIA, key="k", data=b"abc", content_type="image/webp")
    assert storage.read(bucket=MEDIA, key="k", max_size=10) == b"abc"
    with pytest.raises(ObjectTooLarge):
        storage.read(bucket=MEDIA, key="k", max_size=2)
    storage.delete(bucket=MEDIA, key="k")
    storage.delete(bucket=MEDIA, key="k")  # deleting twice is fine
    assert storage.head(bucket=MEDIA, key="k") is None


def test_public_urls_use_the_media_domain(settings):
    settings.MEDIA_BASE_URL = "https://media.example.com/"
    assert FakeStorage().public_url("media/x/large.webp") == (
        "https://media.example.com/media/x/large.webp"
    )


# --- the S3 adapter, without any network ---


@pytest.fixture
def s3(settings):
    settings.STORAGE_ACCESS_KEY_ID = "test-key"
    settings.STORAGE_SECRET_ACCESS_KEY = "test-secret"  # noqa: S105
    settings.STORAGE_REGION = "eu-west-1"
    settings.STORAGE_ENDPOINT_URL = ""
    return S3Storage()


def policy_of(form):
    return json.loads(base64.b64decode(form.fields["policy"]))


def test_the_presigned_form_limits_size_and_type_at_storage(s3):
    form = s3.presign_post(
        bucket=QUARANTINE,
        key="profile_photo/abc",
        content_type="image/png",
        max_size=500,
        expires_in=900,
    )
    assert "wo-quarantine" in form.url
    assert form.fields["key"] == "profile_photo/abc"
    assert form.fields["Content-Type"] == "image/png"
    assert form.fields["x-amz-signature"]
    conditions = policy_of(form)["conditions"]
    assert ["content-length-range", 1, 500] in conditions
    assert {"Content-Type": "image/png"} in conditions
    assert {"bucket": "wo-quarantine"} in conditions
    assert form.expires_in == 900


def test_head_distinguishes_missing_from_present(s3):
    with Stubber(s3.client) as stub:
        stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
        stub.add_response(
            "head_object",
            {"ContentLength": 10, "ContentType": "image/png"},
            {"Bucket": "wo-quarantine", "Key": "k"},
        )
        assert s3.head(bucket=QUARANTINE, key="k") is None
        found = s3.head(bucket=QUARANTINE, key="k")
        assert (found.size, found.content_type) == (10, "image/png")


def test_other_storage_errors_are_not_hidden(s3):
    from botocore.exceptions import ClientError

    with Stubber(s3.client) as stub:
        stub.add_client_error("head_object", service_error_code="403", http_status_code=403)
        with pytest.raises(ClientError):
            s3.head(bucket=QUARANTINE, key="k")


def body(data):
    return StreamingBody(io.BytesIO(data), len(data))


def test_reads_stop_at_the_size_limit(s3):
    with Stubber(s3.client) as stub:
        stub.add_response("get_object", {"Body": body(b"12345")})
        stub.add_response("get_object", {"Body": body(b"1234567890")})
        assert s3.read(bucket=QUARANTINE, key="k", max_size=5) == b"12345"
        with pytest.raises(ObjectTooLarge):
            s3.read(bucket=QUARANTINE, key="k", max_size=5)


def test_writes_send_type_and_caching_headers(s3):
    with Stubber(s3.client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "wo-media",
                "Key": "media/x/large.webp",
                "Body": b"data",
                "ContentType": "image/webp",
                "ContentDisposition": "inline",
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
        s3.write(
            bucket=MEDIA,
            key="media/x/large.webp",
            data=b"data",
            content_type="image/webp",
            cache_control="public, max-age=31536000, immutable",
        )
        stub.assert_no_pending_responses()


def test_delete_targets_the_right_bucket(s3):
    with Stubber(s3.client) as stub:
        stub.add_response("delete_object", {}, {"Bucket": "wo-quarantine", "Key": "k"})
        s3.delete(bucket=QUARANTINE, key="k")
        stub.assert_no_pending_responses()


def test_a_custom_endpoint_uses_path_style_for_minio(settings):
    settings.STORAGE_ENDPOINT_URL = "http://localhost:9000"
    settings.STORAGE_ACCESS_KEY_ID = "minio"
    settings.STORAGE_SECRET_ACCESS_KEY = "minio-secret"  # noqa: S105
    form = S3Storage().presign_post(
        bucket=QUARANTINE, key="k", content_type="image/png", max_size=10, expires_in=60
    )
    assert form.url == "http://localhost:9000/wo-quarantine"
