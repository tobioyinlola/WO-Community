"""The life of an upload: request, receive, check, publish, attach, clean up.

Files only ever move one way. A raw upload sits in the private quarantine
bucket until a worker has verified its real type, scanned it and re-encoded it;
only the re-encoded copies reach the media bucket. Nothing in quarantine is
ever served.
"""

import hashlib
import secrets
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core import ratelimit
from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.integrations.malware import get_scanner
from apps.integrations.storage import MEDIA, QUARANTINE, ObjectTooLarge, PresignedPost, get_storage
from apps.uploads import events, images
from apps.uploads.models import Upload, UploadPurpose, UploadStatus

logger = structlog.get_logger(__name__)

IMMUTABLE = "public, max-age=31536000, immutable"
VARIANTS = ("large", "thumb")


# --- requesting ---


def request_upload(
    *, owner_id: UUID, purpose: str, content_type: str, size: int, filename: str = ""
) -> tuple[Upload, PresignedPost]:
    """Reserve an upload and return the form the client posts the file to."""
    if purpose not in UploadPurpose.values:
        raise exceptions.ValidationError({"purpose": ["Unknown purpose."]})
    if content_type not in settings.UPLOAD_ALLOWED_TYPES:
        allowed = ", ".join(settings.UPLOAD_ALLOWED_TYPES)
        raise exceptions.ValidationError({"content_type": [f"Allowed types: {allowed}."]})
    if not 1 <= size <= settings.UPLOAD_MAX_BYTES:
        limit = settings.UPLOAD_MAX_BYTES // (1024 * 1024)
        raise exceptions.ValidationError(
            {"size": [f"Files must be between 1 byte and {limit} MB."]}
        )
    today = timezone.now().date().isoformat()
    if ratelimit.hit(f"uploads:{owner_id}:{today}", 86400) > settings.UPLOAD_DAILY_LIMIT:
        raise exceptions.Throttled(wait=3600, detail="Daily upload limit reached.")

    key = f"{purpose}/{secrets.token_hex(20)}"  # never derived from anything the client sent
    upload = Upload.objects.create(
        owner_id=owner_id,
        purpose=purpose,
        declared_content_type=content_type,
        declared_size=size,
        original_filename=plain(filename)[:255],
        quarantine_key=key,
        expires_at=timezone.now() + _seconds(settings.UPLOAD_PRESIGN_TTL_SECONDS),
    )
    post = get_storage().presign_post(
        bucket=QUARANTINE,
        key=key,
        content_type=content_type,
        max_size=size,
        expires_in=settings.UPLOAD_PRESIGN_TTL_SECONDS,
    )
    return upload, post


def _seconds(value: int) -> Any:
    from datetime import timedelta

    return timedelta(seconds=value)


def get_owned(owner_id: UUID, upload_id: UUID) -> Upload:
    """An upload, only if it belongs to this user. Others see 404, not 403."""
    upload = Upload.objects.filter(pk=upload_id, owner_id=owner_id).first()
    if upload is None:
        raise exceptions.NotFound()
    return upload


# --- receiving ---


def complete_upload(*, owner_id: UUID, upload_id: UUID) -> Upload:
    """The client says the file is uploaded. Check it arrived and queue the checks.

    Safe to call again: an upload already past this step is returned unchanged.
    """
    storage = get_storage()
    window_closed = False
    with transaction.atomic():
        upload = Upload.objects.select_for_update().filter(pk=upload_id, owner_id=owner_id).first()
        if upload is None:
            raise exceptions.NotFound()
        if upload.status != UploadStatus.PENDING:
            return upload
        if upload.expires_at <= timezone.now():
            _finish(upload, UploadStatus.EXPIRED, "expired")
            window_closed = True  # raised after the block: an error inside would undo the change
        else:
            info = storage.head(bucket=QUARANTINE, key=upload.quarantine_key)
            if info is None:
                raise ConflictError("The file has not arrived yet.", code="upload_missing")
            if info.size < 1 or info.size > upload.declared_size:
                _finish(upload, UploadStatus.REJECTED, "size_mismatch")
            else:
                upload.status = UploadStatus.PROCESSING
                upload.confirmed_at = timezone.now()
                upload.save(update_fields=["status", "confirmed_at", "updated_at"])
                domain_events.publish(events.UploadConfirmed(upload_id=str(upload.pk)))
    if window_closed:
        raise ConflictError("The upload window has closed. Start again.", code="upload_expired")
    return upload


def _finish(upload: Upload, status: str, reason: str) -> None:
    """End an upload that will not be used and remove its raw file."""
    upload.status = status
    upload.reject_reason = reason
    upload.save(update_fields=["status", "reject_reason", "updated_at"])
    get_storage().delete(bucket=QUARANTINE, key=upload.quarantine_key)


# --- checking (runs in a worker) ---


def process_upload(upload_id: UUID) -> None:
    """Verify, scan, re-encode and publish one upload. Safe to run twice.

    If the scanner cannot answer the exception propagates and the task is
    retried; a file is never published without a clean verdict.
    """
    storage = get_storage()
    with transaction.atomic():
        upload = Upload.objects.select_for_update().filter(pk=upload_id).first()
        if upload is None or upload.status != UploadStatus.PROCESSING:
            return
        try:
            data = storage.read(
                bucket=QUARANTINE, key=upload.quarantine_key, max_size=upload.declared_size
            )
        except (ObjectTooLarge, KeyError):
            _finish(upload, UploadStatus.REJECTED, "size_mismatch")
            return
        verdict = get_scanner().scan(data)
        if not verdict.clean:
            logger.warning(
                "upload_malware_detected", upload_id=str(upload.pk), detail=verdict.detail
            )
            audit.record(
                actor=None,
                action="upload.malware_detected",
                target_type="upload",
                target_id=upload.pk,
                after={"owner": str(upload.owner_id), "signature": verdict.detail},
            )
            _finish(upload, UploadStatus.REJECTED, "malware_detected")
            return
        try:
            processed = images.process(data, upload.declared_content_type)
        except images.ImageRejected as exc:
            _finish(upload, UploadStatus.REJECTED, exc.code)
            return

        base = f"media/{upload.purpose}/{secrets.token_hex(16)}"
        for variant, body in (("large", processed.large), ("thumb", processed.thumb)):
            storage.write(
                bucket=MEDIA,
                key=f"{base}/{variant}.webp",
                data=body,
                content_type="image/webp",
                cache_control=IMMUTABLE,
            )
        upload.base_key = base
        upload.width, upload.height = processed.width, processed.height
        upload.checksum = hashlib.sha256(data).hexdigest()
        upload.status = UploadStatus.READY
        upload.ready_at = timezone.now()
        upload.save()
        storage.delete(bucket=QUARANTINE, key=upload.quarantine_key)


def store_external_image(data: bytes, folder: str) -> str:
    """Check, scan, re-encode and publish an image that did not come through an upload.

    Used for pictures we fetched ourselves, such as a link preview's. The bytes get exactly the
    same treatment as a member's upload: type sniffed from the content, scanned, decoded and
    written again, and published under a random key. Returns the base key.
    Raises ``images.ImageRejected`` if the image is not acceptable.
    """
    content_type = images.sniff(data)
    if content_type is None:
        raise images.ImageRejected("not_an_image")
    verdict = get_scanner().scan(data)
    if not verdict.clean:
        logger.warning("external_image_malware_detected", detail=verdict.detail)
        raise images.ImageRejected("malware_detected")
    processed = images.process(data, content_type)
    storage = get_storage()
    base = f"media/{folder}/{secrets.token_hex(16)}"
    for variant, body in (("large", processed.large), ("thumb", processed.thumb)):
        storage.write(
            bucket=MEDIA,
            key=f"{base}/{variant}.webp",
            data=body,
            content_type="image/webp",
            cache_control=IMMUTABLE,
        )
    return base


# --- using ---


def image_urls(base_key: str) -> dict[str, str] | None:
    """Public addresses of an image's variants, or None if there is no image."""
    if not base_key:
        return None
    storage = get_storage()
    return {name: storage.public_url(f"{base_key}/{name}.webp") for name in VARIANTS}


def claim(*, upload_id: UUID, owner_id: UUID, purpose: str) -> Upload:
    """Take a ready upload to attach it somewhere. An upload can be attached only once."""
    upload = Upload.objects.select_for_update().filter(pk=upload_id, owner_id=owner_id).first()
    problem = None
    if upload is None:
        problem = "No such upload."
    elif upload.purpose != purpose:
        problem = "This upload was made for something else."
    elif upload.status != UploadStatus.READY:
        problem = "The upload is not ready yet."
    elif upload.claimed_at is not None:
        problem = "This upload is already in use."
    if problem or upload is None:
        raise exceptions.ValidationError({"upload_id": [problem or "No such upload."]})
    upload.claimed_at = timezone.now()
    upload.save(update_fields=["claimed_at", "updated_at"])
    return upload


def release(base_key: str) -> None:
    """Delete the files of an image that is no longer used, once the change has committed."""
    if not base_key:
        return

    def delete_files() -> None:
        storage = get_storage()
        for name in VARIANTS:
            storage.delete(bucket=MEDIA, key=f"{base_key}/{name}.webp")
        Upload.objects.filter(base_key=base_key).update(status=UploadStatus.DISCARDED)

    transaction.on_commit(delete_files)


# --- housekeeping ---


def cleanup() -> dict[str, int]:
    """Expire stale uploads and delete files nobody will use. Safe to run any time."""
    now = timezone.now()
    storage = get_storage()
    counts = {"expired": 0, "timed_out": 0, "discarded": 0, "purged": 0}

    for upload in Upload.objects.filter(status=UploadStatus.PENDING, expires_at__lte=now):
        _finish(upload, UploadStatus.EXPIRED, "expired")
        counts["expired"] += 1

    stuck = Upload.objects.filter(
        status=UploadStatus.PROCESSING, confirmed_at__lte=now - settings.UPLOAD_PROCESSING_TIMEOUT
    )
    for upload in stuck:
        _finish(upload, UploadStatus.REJECTED, "processing_timeout")
        counts["timed_out"] += 1

    unclaimed = Upload.objects.filter(
        status=UploadStatus.READY,
        claimed_at__isnull=True,
        ready_at__lte=now - settings.UPLOAD_UNCLAIMED_TTL,
    )
    for upload in unclaimed:
        for name in VARIANTS:
            storage.delete(bucket=MEDIA, key=f"{upload.base_key}/{name}.webp")
        upload.status = UploadStatus.DISCARDED
        upload.save(update_fields=["status", "updated_at"])
        counts["discarded"] += 1

    finished = Upload.objects.filter(
        status__in=[UploadStatus.REJECTED, UploadStatus.EXPIRED, UploadStatus.DISCARDED],
        updated_at__lte=now - settings.UPLOAD_RECORD_RETENTION,
    )
    counts["purged"], _ = finished.delete()
    return counts
