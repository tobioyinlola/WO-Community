from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class UploadPurpose(models.TextChoices):
    PROFILE_PHOTO = "profile_photo"
    STARTUP_LOGO = "startup_logo"
    POST_IMAGE = "post_image"
    EDITORIAL_COVER = "editorial_cover"
    CAMPAIGN_IMAGE = "campaign_image"
    COURSE_COVER = "course_cover"


class UploadStatus(models.TextChoices):
    PENDING = "pending"  # the client may upload to the quarantine bucket
    PROCESSING = "processing"  # received; being checked and re-encoded
    READY = "ready"  # safe, re-encoded, in the media bucket
    REJECTED = "rejected"
    EXPIRED = "expired"  # never arrived in time
    DISCARDED = "discarded"  # ready but never attached, or replaced; files deleted


class Upload(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="uploads"
    )
    purpose = models.CharField(max_length=20, choices=UploadPurpose.choices)
    status = models.CharField(
        max_length=12, choices=UploadStatus.choices, default=UploadStatus.PENDING
    )
    declared_content_type = models.CharField(max_length=40)
    declared_size = models.PositiveIntegerField()
    # Kept as metadata only. Storage keys are random and never contain it.
    original_filename = models.CharField(max_length=255, blank=True)
    quarantine_key = models.CharField(max_length=200, unique=True)
    # Prefix of the processed files in the media bucket: <base>/large.webp and <base>/thumb.webp.
    base_key = models.CharField(max_length=200, blank=True)
    reject_reason = models.CharField(max_length=40, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True)
    expires_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=UploadStatus.values), name="upload_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(purpose__in=UploadPurpose.values), name="upload_purpose_valid"
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "created_at"], name="upload_owner_idx"),
            models.Index(fields=["status", "expires_at"], name="upload_status_expiry_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.purpose} {self.status}"
