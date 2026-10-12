from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

OUTPUT_TYPES = ("score", "plan", "forecast", "deck", "prototype")
OUTPUT_STATUSES = ("not_started", "generating", "ready", "needs_refresh", "failed")
VENTURE_STATUSES = ("active", "archived")
STAGES = ("idea", "prototype", "launched", "revenue")


class Venture(BaseModel):
    """One venture a member is working on. Everything about it is private to its owner."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="toolkit_ventures"
    )
    name = models.CharField(max_length=80)
    status = models.CharField(max_length=10, default="active")
    profile_completeness = models.PositiveSmallIntegerField(default=0)
    imported_from_startup = models.ForeignKey(
        "startups.Startup", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    # Deleting hides the venture now and erases it for good after the grace period.
    deleted_at = models.DateTimeField(null=True, blank=True)
    # A member can switch the weekly next steps digest off per venture.
    nudges_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=VENTURE_STATUSES), name="tk_venture_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(profile_completeness__lte=100), name="tk_venture_completeness_range"
            ),
        ]
        indexes = [
            models.Index(
                fields=["owner", "deleted_at", "-created_at"], name="tk_venture_owner_idx"
            ),
            models.Index(fields=["deleted_at"], name="tk_venture_deleted_idx"),
        ]


class VentureProfile(BaseModel):
    venture = models.OneToOneField(Venture, on_delete=models.CASCADE, related_name="profile")
    version = models.PositiveIntegerField(default=1)
    # Validated against ``schema.ProfileFields``; kept as JSON because the wizard is stepwise.
    fields = models.JSONField(default=dict)
    # Per field: where the value came from and when it last changed.
    field_meta = models.JSONField(default=dict)


class VentureProfileVersion(BaseModel):
    venture = models.ForeignKey(Venture, on_delete=models.CASCADE, related_name="profile_versions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    changed_fields = models.JSONField(default=list)
    actor = models.CharField(max_length=24, default="member")  # member, import, change_set

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["venture", "version"], name="tk_profile_version_unique")
        ]
        ordering = ["-version"]


class Competitor(BaseModel):
    venture = models.ForeignKey(Venture, on_delete=models.CASCADE, related_name="competitors")
    name = models.CharField(max_length=120)
    website = models.CharField(max_length=300, blank=True)
    differentiator = models.CharField(max_length=500, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]


class TeamMember(BaseModel):
    venture = models.ForeignKey(Venture, on_delete=models.CASCADE, related_name="team")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    linkedin = models.CharField(max_length=300, blank=True)
    is_founder = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]


class OutputState(BaseModel):
    """Whether one output of a venture is current, being made, or out of date."""

    venture = models.ForeignKey(Venture, on_delete=models.CASCADE, related_name="outputs")
    output_type = models.CharField(max_length=10)
    output_id = models.UUIDField(null=True, blank=True)  # decks and prototypes are many per venture
    status = models.CharField(max_length=14, default="not_started")
    stale_fields = models.JSONField(default=list)
    last_generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(output_type__in=OUTPUT_TYPES), name="tk_output_type_valid"
            ),
            models.CheckConstraint(
                condition=Q(status__in=OUTPUT_STATUSES), name="tk_output_status_valid"
            ),
            models.UniqueConstraint(
                fields=["venture", "output_type", "output_id"],
                name="tk_output_unique",
                nulls_distinct=False,
            ),
        ]


class VentureGrant(BaseModel):
    """A venture shared with one named member (a mentor): read, or read and comment."""

    venture = models.ForeignKey(Venture, on_delete=models.CASCADE, related_name="grants")
    grantee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="toolkit_grants"
    )
    can_comment = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["venture", "grantee"],
                condition=Q(revoked_at__isnull=True),
                name="tk_grant_one_active",
            )
        ]
