from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.ids import uuid7
from apps.core.models import BaseModel


class AnalyticsEvent(models.Model):
    """One thing that happened. Append only and partitioned by month.

    Created by raw SQL in the initial migration, so Django does not manage it.
    Rows are never updated; the forwarder tracks its progress with ``seq``
    instead. Properties are limited by the registry to numbers, flags and short
    identifiers, never free text.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    seq = models.BigIntegerField()
    name = models.CharField(max_length=60)
    actor_id = models.UUIDField(null=True)
    anonymous_id = models.UUIDField(null=True)
    properties = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    source = models.CharField(max_length=10)  # "server" or "client"
    occurred_at = models.DateTimeField()
    received_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "analytics_event"

    def __str__(self) -> str:
        return f"{self.seq} {self.name}"


class AnalyticsPreference(BaseModel):
    """A member's choice to be left out of analytics altogether."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analytics_preference"
    )
    opted_out = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.user_id} opted_out={self.opted_out}"


class IdentityLink(BaseModel):
    """Ties a visitor's anonymous id to the member they became, so the funnel is continuous."""

    anonymous_id = models.UUIDField(unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analytics_links"
    )
    forwarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["forwarded_at"], name="identity_pending_idx")]

    def __str__(self) -> str:
        return f"{self.anonymous_id} -> {self.user_id}"


class ForwardCursor(models.Model):
    """How far the forwarder has got, per destination."""

    name = models.CharField(max_length=40, primary_key=True)
    last_seq = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.name}@{self.last_seq}"
