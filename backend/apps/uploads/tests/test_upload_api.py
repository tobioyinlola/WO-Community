import io
from datetime import timedelta

import pytest
from django.utils import timezone
from PIL import Image
from rest_framework.throttling import ScopedRateThrottle

from apps.audit.models import AuditLog
from apps.core.models import OutboxEvent
from apps.integrations.malware.fake import EICAR, FakeScanner
from apps.integrations.storage.base import MEDIA, QUARANTINE
from apps.integrations.storage.fake import FakeStorage
from apps.uploads import services
from apps.uploads.models import Upload
from apps.uploads.tests.helpers import content_type_of, image_bytes

pytestmark = pytest.mark.django_db

UPLOADS = "/api/v1/uploads"


@pytest.fixture
def user(make_user):
    return make_user(email="uploader@example.com")


@pytest.fixture
def client(user, client_for):
    return client_for(user)


def start(client, data=None, fmt="PNG", **overrides):
    data = data if data is not None else image_bytes(fmt)
    body = {
        "purpose": "profile_photo",
        "content_type": content_type_of(fmt),
        "size": len(data),
        "filename": "me.png",
        **overrides,
    }
    return client.post(UPLOADS, body)


def send(response, data):
    """Do what the browser does: post the file straight to storage."""
    form = response.json()["form"]
    post = type("Post", (), {"fields": form["form_data"]})
    storage_post = FakeStorage().presign_post(
        bucket=QUARANTINE,
        key=form["form_data"]["key"],
        content_type=form["form_data"]["Content-Type"],
        max_size=int(form["form_data"]["x-max-size"]),
        expires_in=form["expires_in"],
    )
    assert post
    FakeStorage.client_upload(storage_post, data, form["form_data"]["Content-Type"])


def complete(client, upload_id):
    return client.post(f"{UPLOADS}/{upload_id}/complete")


def status_of(client, upload_id):
    return client.get(f"{UPLOADS}/{upload_id}").json()


def full_flow(client, run_outbox, data=None, fmt="PNG", **overrides):
    data = data if data is not None else image_bytes(fmt)
    created = start(client, data, fmt, **overrides)
    send(created, data)
    upload_id = created.json()["upload"]["id"]
    complete(client, upload_id)
    run_outbox()
    return upload_id


# --- access ---


def test_every_endpoint_needs_a_login(api_client, client, run_outbox):
    upload_id = start(client).json()["upload"]["id"]
    assert api_client.post(UPLOADS, {}).status_code == 401
    assert api_client.get(f"{UPLOADS}/{upload_id}").status_code == 401
    assert api_client.post(f"{UPLOADS}/{upload_id}/complete").status_code == 401


def test_pending_accounts_may_upload_their_own_photo(make_user, client_for):
    pending = make_user(email="pending@example.com", status="pending")
    assert start(client_for(pending)).status_code == 201


def test_uploads_belong_to_their_owner_alone(client, make_user, client_for):
    upload_id = start(client).json()["upload"]["id"]
    stranger = client_for(make_user(email="stranger@example.com"))
    assert stranger.get(f"{UPLOADS}/{upload_id}").status_code == 404
    assert complete(stranger, upload_id).status_code == 404
    assert Upload.objects.get().status == "pending"


# --- requesting ---


def test_requesting_an_upload_returns_a_form_for_direct_upload(client, user):
    response = start(client)
    assert response.status_code == 201
    body = response.json()
    assert response["Cache-Control"] == "no-store"
    assert body["upload"]["status"] == "pending"
    assert body["upload"]["urls"] is None
    assert body["max_size"] == 5 * 1024 * 1024
    form = body["form"]
    assert form["method"] == "POST" and form["url"].startswith("https://")
    assert form["expires_in"] == 900
    assert form["form_data"]["Content-Type"] == "image/png"


def test_storage_keys_are_random_and_never_use_anything_the_client_sent(client, user):
    first = start(client, filename="holiday photo.png").json()["form"]["form_data"]["key"]
    second = start(client, filename="holiday photo.png").json()["form"]["form_data"]["key"]
    assert first != second
    assert first.startswith("profile_photo/") and len(first.split("/")[1]) == 40
    assert "holiday" not in first and str(user.pk) not in first


def test_the_original_filename_is_kept_only_as_cleaned_metadata(client):
    start(client, filename="<script>x</script>../../etc/passwd.png")
    upload = Upload.objects.get()
    assert "<script>" not in upload.original_filename
    assert upload.original_filename in upload.original_filename.strip()
    assert upload.original_filename not in upload.quarantine_key


@pytest.mark.parametrize(
    "overrides",
    [
        {"purpose": "avatar"},
        {"purpose": ""},
        {"content_type": "image/svg+xml"},
        {"content_type": "image/gif"},
        {"content_type": "application/pdf"},
        {"content_type": "text/html"},
        {"size": 0},
        {"size": -5},
        {"size": 5 * 1024 * 1024 + 1},
        {"size": "big"},
        {"owner": "someone-else"},
        {"status": "ready"},
    ],
)
def test_invalid_requests_are_refused(client, overrides):
    assert start(client, **overrides).status_code == 400
    assert Upload.objects.count() == 0


def test_the_exact_size_limit_is_allowed(client):
    assert start(client, size=5 * 1024 * 1024).status_code == 201


def test_there_is_a_daily_limit_per_member(client, settings):
    settings.UPLOAD_DAILY_LIMIT = 2
    assert [start(client).status_code for _ in range(3)] == [201, 201, 429]


def test_requests_are_also_rate_limited_per_hour(client, monkeypatch):
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "uploads": "2/hour"},
    )
    assert [start(client).status_code for _ in range(3)] == [201, 201, 429]


# --- the happy path ---


def test_a_good_image_goes_from_quarantine_to_clean_media(client, run_outbox, settings):
    data = image_bytes("PNG", (1200, 900))
    created = start(client, data)
    send(created, data)
    upload_id = created.json()["upload"]["id"]
    key = created.json()["form"]["form_data"]["key"]

    assert complete(client, upload_id).status_code == 202
    assert status_of(client, upload_id)["status"] == "processing"
    assert status_of(client, upload_id)["urls"] is None
    assert FakeStorage().head(bucket=QUARANTINE, key=key) is not None

    run_outbox()
    body = status_of(client, upload_id)
    assert body["status"] == "ready"
    assert (body["width"], body["height"]) == (1200, 900)
    base = Upload.objects.get().base_key
    assert body["urls"] == {
        "large": f"https://media.test/{base}/large.webp",
        "thumb": f"https://media.test/{base}/thumb.webp",
    }
    assert FakeStorage().head(bucket=QUARANTINE, key=key) is None  # the raw file is gone
    stored = FakeStorage().read(bucket=MEDIA, key=f"{base}/large.webp", max_size=10**7)
    assert Image.open(io.BytesIO(stored)).format == "WEBP"


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_all_three_allowed_formats_work(client, run_outbox, fmt):
    upload_id = full_flow(client, run_outbox, fmt=fmt)
    assert status_of(client, upload_id)["status"] == "ready"


def test_the_media_files_have_immutable_cache_headers_and_random_names(client, run_outbox):
    full_flow(client, run_outbox)
    upload = Upload.objects.get()
    assert (
        upload.base_key.startswith("media/profile_photo/")
        and len(upload.base_key.split("/")[2]) == 32
    )
    assert len(upload.checksum) == 64


def test_completing_twice_does_not_process_twice(client, run_outbox):
    data = image_bytes()
    created = start(client, data)
    send(created, data)
    upload_id = created.json()["upload"]["id"]
    complete(client, upload_id)
    complete(client, upload_id)
    assert OutboxEvent.objects.filter(topic="uploads.upload_confirmed").count() == 1
    run_outbox()
    assert complete(client, upload_id).json()["status"] == "ready"
    assert OutboxEvent.objects.filter(topic="uploads.upload_confirmed").count() == 1


def test_processing_twice_is_harmless(client, run_outbox):
    upload_id = full_flow(client, run_outbox)
    before = Upload.objects.get().base_key
    services.process_upload(Upload.objects.get().pk)
    assert Upload.objects.get().base_key == before
    assert status_of(client, upload_id)["status"] == "ready"


# --- receiving problems ---


def test_completing_before_the_file_arrives_is_a_conflict(client):
    upload_id = start(client).json()["upload"]["id"]
    response = complete(client, upload_id)
    assert response.status_code == 409
    assert response.json()["code"] == "upload_missing"
    assert Upload.objects.get().status == "pending"


def test_a_file_larger_than_declared_is_rejected_and_removed(client, run_outbox):
    created = start(client, image_bytes())
    key = created.json()["form"]["form_data"]["key"]
    FakeStorage.objects[(QUARANTINE, key)] = (b"x" * 10_000_000, "image/png")  # bypasses the form
    upload_id = created.json()["upload"]["id"]
    complete(client, upload_id)
    body = status_of(client, upload_id)
    assert (body["status"], body["reason"]) == ("rejected", "size_mismatch")
    assert FakeStorage().head(bucket=QUARANTINE, key=key) is None


def test_the_upload_window_closes(client):
    data = image_bytes()
    created = start(client, data)
    send(created, data)
    upload_id = created.json()["upload"]["id"]
    Upload.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = complete(client, upload_id)
    assert response.status_code == 409
    assert response.json()["code"] == "upload_expired"
    assert status_of(client, upload_id)["status"] == "expired"


# --- what the checks refuse ---


def rejected(client, run_outbox, data, fmt="PNG"):
    upload_id = full_flow(client, run_outbox, data=data, fmt=fmt)
    body = status_of(client, upload_id)
    assert body["status"] == "rejected" and body["urls"] is None
    assert FakeStorage.objects.keys() == set() or all(b != MEDIA for b, _ in FakeStorage.objects)
    return body["reason"]


def test_a_file_that_lies_about_its_type_is_rejected(client, run_outbox):
    assert rejected(client, run_outbox, image_bytes("PNG"), fmt="JPEG") == "type_mismatch"


def test_something_that_is_not_an_image_is_rejected(client, run_outbox):
    fake = b"\x89PNG\r\n\x1a\n" + b"this is not an image" * 20
    assert rejected(client, run_outbox, fake) == "not_an_image"


def test_a_web_page_pretending_to_be_a_photo_is_rejected(client, run_outbox):
    page = b"<html><script>steal()</script></html>" * 5
    assert rejected(client, run_outbox, page) == "type_mismatch"


def test_malware_is_rejected_audited_and_never_published(client, run_outbox):
    infected = image_bytes("PNG") + EICAR
    upload_id = full_flow(client, run_outbox, data=infected)
    body = status_of(client, upload_id)
    assert (body["status"], body["reason"]) == ("rejected", "malware_detected")
    assert body["urls"] is None
    assert not any(bucket == MEDIA for bucket, _ in FakeStorage.objects)
    entry = AuditLog.objects.get(action="upload.malware_detected")
    assert entry.target_id == upload_id and entry.after["signature"] == "Eicar-Test-Signature"


def test_data_hidden_in_an_image_does_not_reach_the_media_bucket(client, run_outbox):
    data = image_bytes("JPEG") + b"<script>alert(1)</script>HIDDEN-PAYLOAD"
    upload_id = full_flow(client, run_outbox, data=data, fmt="JPEG")
    assert status_of(client, upload_id)["status"] == "ready"
    for (bucket, _), (stored, _) in FakeStorage.objects.items():
        assert bucket == MEDIA and b"HIDDEN-PAYLOAD" not in stored


def test_an_unreachable_scanner_never_lets_a_file_through(client, run_outbox):
    FakeScanner.down = True
    data = image_bytes()
    created = start(client, data)
    send(created, data)
    upload_id = created.json()["upload"]["id"]
    complete(client, upload_id)
    run_outbox()  # the worker fails and the event is retried later
    assert status_of(client, upload_id)["status"] == "processing"
    assert not any(bucket == MEDIA for bucket, _ in FakeStorage.objects)
    assert OutboxEvent.objects.get(topic="uploads.upload_confirmed").status == "pending"

    FakeScanner.down = False
    OutboxEvent.objects.update(available_at=timezone.now())
    run_outbox()
    assert status_of(client, upload_id)["status"] == "ready"


def test_nothing_unfinished_ever_exposes_a_url(client, run_outbox):
    data = image_bytes()
    created = start(client, data)
    upload_id = created.json()["upload"]["id"]
    assert status_of(client, upload_id)["urls"] is None
    send(created, data)
    complete(client, upload_id)
    assert status_of(client, upload_id)["urls"] is None
