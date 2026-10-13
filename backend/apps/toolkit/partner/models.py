from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

CHANGE_STATUSES = ("proposed", "applied", "undone", "dismissed")
ROLES = ("user", "assistant")


class Conversation(BaseModel):
    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="conversations"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="toolkit_conversations"
    )
    title = models.CharField(max_length=120, blank=True)

    class Meta:
        indexes = [models.Index(fields=["venture", "-updated_at"], name="tk_conv_venture_idx")]


class Message(BaseModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10)
    text = models.TextField()
    # What the assistant did besides talk: {"declined": "legal", "next_steps": [...], ...}
    meta = models.JSONField(default=dict)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(role__in=ROLES), name="tk_message_role_valid")
        ]


class ChangeSet(BaseModel):
    """Profile changes the assistant proposed. Nothing is written until the member applies it."""

    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="change_sets"
    )
    message = models.OneToOneField(
        Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="change_set"
    )
    status = models.CharField(max_length=10, default="proposed")
    # [{field, label, from, to, reason, applied}] where from and to are the values themselves.
    changes = models.JSONField(default=list)
    applied_at = models.DateTimeField(null=True, blank=True)
    undone_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=CHANGE_STATUSES), name="tk_changeset_status_valid"
            )
        ]


class Decision(BaseModel):
    """A choice the founder recorded, so the assistant sees why things are as they are."""

    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="decisions"
    )
    text = models.CharField(max_length=300)
    rationale = models.CharField(max_length=1000, blank=True)
    decided_on = models.DateField()

    class Meta:
        ordering = ["-decided_on", "-created_at"]


class Nudge(BaseModel):
    """One suggested next step for a venture, at most one per week."""

    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="nudges"
    )
    week_key = models.CharField(max_length=10)  # e.g. 2026-W41
    code = models.CharField(max_length=40)
    text = models.CharField(max_length=300)
    action = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["venture", "week_key"], name="tk_nudge_one_per_week")
        ]
