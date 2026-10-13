from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

SUBJECT_TYPES = ("deck", "prototype", "plan_summary", "score_summary")


class ShareLink(BaseModel):
    """A read only link to one deck, prototype or summary. Only a hash of the token is stored."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="toolkit_shares"
    )
    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="share_links"
    )
    subject_type = models.CharField(max_length=14)
    subject_id = models.UUIDField()
    token_hash = models.CharField(max_length=64, unique=True)
    password_hash = models.CharField(max_length=200, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(subject_type__in=SUBJECT_TYPES), name="tk_share_subject_valid"
            )
        ]
        indexes = [models.Index(fields=["subject_type", "subject_id"], name="tk_share_subject_idx")]
