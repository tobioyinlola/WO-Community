from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

ROLES = ("user", "assistant")


class AdvisorMessage(BaseModel):
    """One message in a member's single, ongoing conversation with Onyeka."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="advisor_messages"
    )
    role = models.CharField(max_length=10)
    text = models.TextField()
    # What the reply carried besides words: {"next_steps": [...], "reply_to": "<id>", ...}
    meta = models.JSONField(default=dict)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["owner", "created_at"], name="tk_advisor_owner_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(role__in=ROLES), name="tk_advisor_role_valid")
        ]
