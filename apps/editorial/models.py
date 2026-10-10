from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

ITEM_TYPES = ("award", "celebration", "partnership", "funding", "news", "announcement")
ITEM_STATUSES = ("draft", "scheduled", "published", "removed")
WIN_KINDS = ("award", "funding", "partnership")
REACTION_KINDS = ("like", "celebrate", "insightful")


class EditorialItem(BaseModel):
    """A news story, award, celebration, partnership, funding round or announcement."""

    class Status(models.TextChoices):
        DRAFT = "draft"
        SCHEDULED = "scheduled"  # goes live by itself at ``publish_at``
        PUBLISHED = "published"
        REMOVED = "removed"

    type = models.CharField(max_length=12)
    slug = models.SlugField(max_length=90, unique=True)
    title = models.CharField(max_length=160)
    body = models.TextField()  # sanitised HTML
    body_text = models.TextField()  # the same words without markup
    cover_key = models.CharField(max_length=200, blank=True)
    external_url = models.CharField(max_length=300, blank=True)
    comments_enabled = models.BooleanField(default=True)
    # Whether the latest items may also appear on the public website.
    public = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    publish_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    # Announcements can also be pinned as a banner on the member home for a set period.
    banner_starts_at = models.DateTimeField(null=True, blank=True)
    banner_ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    comment_count = models.PositiveIntegerField(default=0)
    reaction_count = models.PositiveIntegerField(default=0)
    reaction_counts = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(type__in=ITEM_TYPES), name="editorial_type_valid"),
            models.CheckConstraint(
                condition=Q(status__in=ITEM_STATUSES), name="editorial_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(banner_starts_at__isnull=True)
                | Q(banner_ends_at__isnull=True)
                | Q(banner_ends_at__gt=models.F("banner_starts_at")),
                name="editorial_banner_window",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-publish_at"], name="editorial_status_idx"),
            models.Index(fields=["-published_at", "-id"], name="editorial_published_idx"),
            models.Index(fields=["type", "-published_at"], name="editorial_type_idx"),
        ]


class ItemStartup(BaseModel):
    item = models.ForeignKey(EditorialItem, on_delete=models.CASCADE, related_name="startup_links")
    startup = models.ForeignKey("startups.Startup", on_delete=models.CASCADE, related_name="+")
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "startup"], name="editorial_startup_once")
        ]
        ordering = ["position"]


class ItemComment(BaseModel):
    item = models.ForeignKey(EditorialItem, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="editorial_comments"
    )
    body = models.TextField()  # sanitised HTML
    hidden_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["item", "created_at", "id"], name="editorial_comment_idx")]


class ItemReaction(BaseModel):
    item = models.ForeignKey(EditorialItem, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="editorial_reactions"
    )
    kind = models.CharField(max_length=12)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "user", "kind"], name="editorial_reaction_unique"
            ),
            models.CheckConstraint(
                condition=Q(kind__in=REACTION_KINDS), name="editorial_reaction_kind"
            ),
        ]


class WinSubmission(BaseModel):
    """A member's claim of an award, funding or partnership, with evidence, for admin review."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"

    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="win_submissions"
    )
    startup = models.ForeignKey(
        "startups.Startup", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=12)
    title = models.CharField(max_length=160)
    evidence_url = models.CharField(max_length=300)
    details = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)
    # The draft story an approval creates, for an editor to polish and publish.
    item = models.ForeignKey(
        EditorialItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(kind__in=WIN_KINDS), name="win_kind_valid"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "approved", "rejected"]),
                name="win_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="win_queue_idx"),
            models.Index(fields=["submitter", "-created_at"], name="win_mine_idx"),
        ]
