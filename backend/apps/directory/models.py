"""Read model for the public directory.

Rows hold only what a visitor may see: they are built from the same visibility
rule used everywhere else, with the public audience. Searching and ranking
therefore can never touch private data. Source records stay the truth; these
rows are rebuilt from them whenever they change.
"""

from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import SearchVectorField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.functions import Upper

from apps.core.models import BaseModel


class PublicStartup(BaseModel):
    startup_id = models.UUIDField(unique=True)
    owner_id = models.UUIDField()
    slug = models.SlugField(max_length=80, unique=True)

    # Filter and sort columns.
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=2)
    sector_slug = models.CharField(max_length=80)
    stage_slug = models.CharField(max_length=80)
    skill_slugs = models.JSONField(default=list)
    featured_rank = models.PositiveSmallIntegerField(default=1)  # 0 featured, 1 not
    newest_key = models.BigIntegerField()  # minus the creation time, so ascending is newest first
    name_key = models.CharField(max_length=120)

    # Text that search reads (description only when it is public).
    pitch = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    sector_name = models.CharField(max_length=80, blank=True)
    founder_names = models.TextField(blank=True)
    skill_names = models.TextField(blank=True)
    search_vector = SearchVectorField(null=True)

    # What the API returns, already shaped and already limited to public data.
    card = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    detail = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    source_updated_at = models.DateTimeField()

    class Meta:
        indexes = [
            GinIndex(fields=["search_vector"], name="pubstartup_search_idx"),
            GinIndex(OpClass(Upper("name"), name="gin_trgm_ops"), name="pubstartup_name_trgm_idx"),
            models.Index(
                fields=["featured_rank", "newest_key", "id"], name="pubstartup_newest_idx"
            ),
            models.Index(fields=["featured_rank", "name_key", "id"], name="pubstartup_name_idx"),
            models.Index(fields=["country"], name="pubstartup_country_idx"),
            models.Index(fields=["sector_slug"], name="pubstartup_sector_idx"),
            models.Index(fields=["stage_slug"], name="pubstartup_stage_idx"),
            models.Index(fields=["owner_id"], name="pubstartup_owner_idx"),
        ]

    def __str__(self) -> str:
        return self.slug


class PublicFounder(BaseModel):
    user_id = models.UUIDField(unique=True)
    slug = models.SlugField(max_length=80, unique=True)

    full_name = models.CharField(max_length=120)
    country = models.CharField(max_length=2, blank=True)
    skill_slugs = models.JSONField(default=list)
    startup_slugs = models.JSONField(default=list)  # lets a startup change find its founders
    newest_key = models.BigIntegerField()
    name_key = models.CharField(max_length=120)

    headline = models.CharField(max_length=160, blank=True)
    bio = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    skill_names = models.TextField(blank=True)
    startup_names = models.TextField(blank=True)
    search_vector = SearchVectorField(null=True)

    card = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    detail = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    source_updated_at = models.DateTimeField()

    class Meta:
        indexes = [
            GinIndex(fields=["search_vector"], name="pubfounder_search_idx"),
            GinIndex(
                OpClass(Upper("full_name"), name="gin_trgm_ops"), name="pubfounder_name_trgm_idx"
            ),
            models.Index(fields=["newest_key", "id"], name="pubfounder_newest_idx"),
            models.Index(fields=["name_key", "id"], name="pubfounder_name_idx"),
            models.Index(fields=["country"], name="pubfounder_country_idx"),
        ]

    def __str__(self) -> str:
        return self.slug
