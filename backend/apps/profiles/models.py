from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class FounderProfile(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="founder_profile"
    )
    slug = models.SlugField(max_length=80, unique=True)
    full_name = models.CharField(max_length=120, blank=True)
    headline = models.CharField(max_length=160, blank=True)
    bio = models.CharField(max_length=500, blank=True)
    country = models.CharField(max_length=2, blank=True)
    city = models.CharField(max_length=100, blank=True)
    skills = models.ManyToManyField("reference.Skill", blank=True, related_name="+")
    custom_skills = models.JSONField(default=list, blank=True)
    open_to = models.JSONField(default=list, blank=True)
    linkedin_url = models.CharField(max_length=300, blank=True)
    x_url = models.CharField(max_length=300, blank=True)
    website_url = models.CharField(max_length=300, blank=True)
    # Storage key of the photo; set by the upload flow, never by the profile API.
    photo_key = models.CharField(max_length=200, blank=True)
    # Only the groups the member changed; the rest use the defaults in domain.py.
    visibility = models.JSONField(default=dict, blank=True)
    completeness_score = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(completeness_score__lte=100), name="profile_score_max_100"
            ),
        ]
        indexes = [models.Index(fields=["country"], name="profile_country_idx")]

    def __str__(self) -> str:
        return self.slug
