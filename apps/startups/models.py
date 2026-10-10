from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel
from apps.startups import domain


class Startup(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_startups"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=80, unique=True)
    country = models.CharField(max_length=2)
    city = models.CharField(max_length=100)
    sector = models.ForeignKey("reference.Sector", on_delete=models.PROTECT, related_name="+")
    stage = models.ForeignKey("reference.Stage", on_delete=models.PROTECT, related_name="+")
    year_founded = models.PositiveSmallIntegerField(null=True, blank=True)
    pitch = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    website_url = models.CharField(max_length=300, blank=True)
    # Storage key of the logo; set by the upload flow, never by the startup API.
    logo_key = models.CharField(max_length=200, blank=True)
    directory_opt_in = models.BooleanField(default=False)
    featured_at = models.DateTimeField(null=True, blank=True)
    visibility = models.JSONField(default=dict, blank=True)
    completeness_score = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(year_founded__isnull=True)
                | models.Q(year_founded__gte=domain.MIN_YEAR, year_founded__lte=2100),
                name="startup_year_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(completeness_score__lte=100), name="startup_score_max_100"
            ),
        ]
        indexes = [
            models.Index(
                fields=["directory_opt_in", "country", "sector", "stage"],
                name="startup_directory_idx",
            ),
            models.Index(fields=["owner"], name="startup_owner_idx"),
        ]

    def __str__(self) -> str:
        return self.slug


class StartupMember(BaseModel):
    """A person on a startup's team: a linked member, or just an email until they join."""

    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="startup_memberships",
    )
    invited_email = models.EmailField(blank=True)
    title = models.CharField(max_length=80, blank=True)
    is_founder = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["startup", "user"],
                condition=models.Q(user__isnull=False),
                name="startupmember_unique_user",
            ),
            models.UniqueConstraint(
                "startup",
                Lower("invited_email"),
                condition=~models.Q(invited_email=""),
                name="startupmember_unique_email",
            ),
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | ~models.Q(invited_email=""),
                name="startupmember_has_identity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.startup_id}:{self.user_id or self.invited_email}"


class TractionMetric(BaseModel):
    startup = models.ForeignKey(Startup, on_delete=models.CASCADE, related_name="traction")
    kind = models.CharField(max_length=20)
    value_int = models.PositiveIntegerField(null=True, blank=True)
    value_text = models.CharField(max_length=300, blank=True)
    as_of_date = models.DateField()
    visibility = models.CharField(max_length=10, default="private")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=domain.TRACTION_KINDS), name="traction_kind_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(visibility__in=["private", "members", "public"]),
                name="traction_visibility_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["startup", "kind", "as_of_date"], name="traction_lookup_idx")
        ]
        ordering = ["kind", "-as_of_date", "created_at"]

    def __str__(self) -> str:
        return f"{self.kind} for {self.startup_id}"
