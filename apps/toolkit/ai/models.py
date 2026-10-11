from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel


class AIRun(BaseModel):
    """One call to a model: what asked, which prompt, how big, how long, how it ended.

    Neither prompts nor outputs are stored here; only identifiers and sizes, so usage can be
    reported without keeping a member's words anywhere else.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    job = models.ForeignKey(
        "tk_jobs.AIJob", null=True, blank=True, on_delete=models.SET_NULL, related_name="runs"
    )
    venture = models.ForeignKey(
        "tk_ventures.Venture", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    agent = models.CharField(max_length=30)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=80)
    prompt_id = models.CharField(max_length=60)
    prompt_version = models.PositiveSmallIntegerField(default=1)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    estimated_cost_minor = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")
    outcome = models.CharField(max_length=20)  # ok, invalid_output, rejected, error, timeout

    class Meta:
        indexes = [
            models.Index(fields=["owner", "created_at"], name="tk_airun_owner_idx"),
            models.Index(fields=["agent", "created_at"], name="tk_airun_agent_idx"),
            models.Index(fields=["created_at"], name="tk_airun_created_idx"),
        ]


class Source(BaseModel):
    """A page a fact came from. Shared and not personal: it holds no member content."""

    url = models.CharField(max_length=1000)
    url_hash = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=300, blank=True)
    publisher = models.CharField(max_length=200, blank=True)
    published_at = models.DateField(null=True, blank=True)
    retrieved_at = models.DateTimeField()
    content_hash = models.CharField(max_length=64, blank=True)
    excerpt = models.TextField(blank=True)


class Fact(BaseModel):
    """A sourced statement from the research store, reused across members' outputs."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="facts")
    topic = models.CharField(max_length=60)  # market_size, growth, competition, regulation, ...
    statement = models.CharField(max_length=600)
    value = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    region = models.CharField(max_length=40, blank=True)
    sector = models.CharField(max_length=80, blank=True)
    confidence = models.DecimalField(max_digits=3, decimal_places=2, default=0.5)
    retrieved_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(confidence__gte=0, confidence__lte=1), name="tk_fact_confidence_range"
            )
        ]
        indexes = [models.Index(fields=["topic", "region", "sector"], name="tk_fact_lookup_idx")]


class ResearchCache(BaseModel):
    """What a search returned for a question, by day, so one venture does not search twice."""

    key = models.CharField(max_length=64, unique=True)  # hash of query, region and day
    fact_ids = models.JSONField(default=list)
