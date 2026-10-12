from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.support import domain


class SupportTicket(BaseModel):
    """One request for help, from a member or from someone who could not sign in."""

    # Shown as SUP-1042. Taken from a database sequence so two requests never share a number.
    number = models.PositiveIntegerField(unique=True)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # What the person gave at the time, kept even if the account changes or is erased.
    name = models.CharField(max_length=120)
    email = models.EmailField()
    category = models.CharField(max_length=20)
    subject = models.CharField(max_length=domain.SUBJECT_MAX)
    status = models.CharField(max_length=16, default="open")
    priority = models.CharField(max_length=6, default="normal")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    last_activity_at = models.DateTimeField()
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reopened_count = models.PositiveSmallIntegerField(default=0)
    satisfaction = models.CharField(max_length=4, blank=True)
    satisfaction_comment = models.CharField(max_length=500, blank=True)
    # Sending the same form twice (a double click, a retry) gives back the first request.
    idempotency_key = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=domain.STATUSES), name="supportticket_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(priority__in=domain.PRIORITIES), name="supportticket_priority_valid"
            ),
            models.CheckConstraint(
                condition=Q(category__in=domain.CATEGORIES), name="supportticket_category_valid"
            ),
            models.UniqueConstraint(
                fields=["member", "idempotency_key"],
                condition=~Q(idempotency_key="") & Q(member__isnull=False),
                name="supportticket_idempotent",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "-last_activity_at"], name="supportticket_status_idx"),
            models.Index(fields=["assignee", "status"], name="supportticket_assignee_idx"),
            models.Index(fields=["-created_at"], name="supportticket_created_idx"),
            models.Index(fields=["member", "-last_activity_at"], name="supportticket_member_idx"),
        ]

    @property
    def reference(self) -> str:
        return f"SUP-{self.number}"


class SupportMessage(BaseModel):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author_type = models.CharField(max_length=6)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Sanitised HTML (a member's plain text is turned into paragraphs) and its plain words.
    body = models.TextField()
    body_text = models.TextField()
    # A note only admins can see.
    is_internal = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(author_type__in=domain.AUTHOR_TYPES), name="supportmessage_author_valid"
            ),
            models.CheckConstraint(
                condition=Q(is_internal=False) | Q(author_type="admin"),
                name="supportmessage_internal_is_admin",
            ),
        ]
        indexes = [models.Index(fields=["ticket", "created_at"], name="supportmessage_ticket_idx")]


class SupportAttachment(BaseModel):
    message = models.ForeignKey(
        SupportMessage, on_delete=models.CASCADE, related_name="attachments"
    )
    upload = models.ForeignKey(
        "uploads.Upload", null=True, on_delete=models.SET_NULL, related_name="+"
    )
    # The object in the private bucket, copied from the upload so a cleanup of uploads is safe.
    storage_key = models.CharField(max_length=200)
    filename = models.CharField(max_length=255)
    size = models.PositiveIntegerField()
    content_type = models.CharField(max_length=100)
    scan_status = models.CharField(max_length=10, default="clean")


class SupportCannedReply(BaseModel):
    """A saved answer an admin can insert into a reply."""

    title = models.CharField(max_length=80)
    body = models.TextField()
    # Blank means it fits any category.
    category = models.CharField(max_length=20, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["title"]
