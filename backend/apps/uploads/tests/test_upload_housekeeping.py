from datetime import timedelta

import pytest
from django.utils import timezone

from apps.integrations.storage.base import MEDIA, QUARANTINE
from apps.integrations.storage.fake import FakeStorage
from apps.uploads import services
from apps.uploads.models import Upload
from apps.uploads.tests.helpers import image_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(make_user):
    return make_user(email="uploader@example.com")


def pending(user):
    data = image_bytes()
    upload, post = services.request_upload(
        owner_id=user.pk, purpose="profile_photo", content_type="image/png", size=len(data)
    )
    FakeStorage.client_upload(post, data, "image/png")
    return upload


def test_pending_uploads_that_never_completed_expire_and_lose_their_file(user):
    upload = pending(user)
    Upload.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    assert services.cleanup()["expired"] == 1
    upload.refresh_from_db()
    assert (upload.status, upload.reject_reason) == ("expired", "expired")
    assert FakeStorage().head(bucket=QUARANTINE, key=upload.quarantine_key) is None


def test_live_pending_uploads_are_left_alone(user):
    upload = pending(user)
    assert services.cleanup()["expired"] == 0
    assert FakeStorage().head(bucket=QUARANTINE, key=upload.quarantine_key) is not None


def test_uploads_stuck_in_processing_are_rejected(user, settings):
    upload = pending(user)
    services.complete_upload(owner_id=user.pk, upload_id=upload.pk)
    Upload.objects.update(confirmed_at=timezone.now() - settings.UPLOAD_PROCESSING_TIMEOUT)
    assert services.cleanup()["timed_out"] == 1
    upload.refresh_from_db()
    assert upload.reject_reason == "processing_timeout"
    assert FakeStorage().head(bucket=QUARANTINE, key=upload.quarantine_key) is None


def test_ready_uploads_nobody_used_are_discarded_with_their_files(user, ready_upload, settings):
    upload = ready_upload(user)
    Upload.objects.update(ready_at=timezone.now() - settings.UPLOAD_UNCLAIMED_TTL)
    assert services.cleanup()["discarded"] == 1
    upload.refresh_from_db()
    assert upload.status == "discarded"
    assert FakeStorage().head(bucket=MEDIA, key=f"{upload.base_key}/large.webp") is None
    assert FakeStorage().head(bucket=MEDIA, key=f"{upload.base_key}/thumb.webp") is None


def test_ready_uploads_that_are_in_use_are_kept(user, ready_upload, settings):
    upload = ready_upload(user)
    Upload.objects.update(
        ready_at=timezone.now() - settings.UPLOAD_UNCLAIMED_TTL, claimed_at=timezone.now()
    )
    assert services.cleanup()["discarded"] == 0
    assert FakeStorage().head(bucket=MEDIA, key=f"{upload.base_key}/large.webp") is not None


def test_old_finished_records_are_purged(user, settings):
    upload = pending(user)
    Upload.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    services.cleanup()
    Upload.objects.update(updated_at=timezone.now() - settings.UPLOAD_RECORD_RETENTION)
    assert services.cleanup()["purged"] == 1
    assert not Upload.objects.filter(pk=upload.pk).exists()


def test_cleanup_is_repeatable(user):
    pending(user)
    Upload.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    services.cleanup()
    assert services.cleanup() == {"expired": 0, "timed_out": 0, "discarded": 0, "purged": 0}
