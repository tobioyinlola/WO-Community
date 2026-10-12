from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel


class SearchRecent(BaseModel):
    """A term someone searched for, kept so the empty search box can offer it again."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="recent_searches"
    )
    term = models.CharField(max_length=100)
    scope = models.CharField(max_length=6, default="member")
    last_used_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "user", Lower("term"), "scope", name="searchrecent_user_term_unique"
            )
        ]
        indexes = [
            models.Index(fields=["user", "scope", "-last_used_at"], name="searchrecent_list_idx")
        ]
