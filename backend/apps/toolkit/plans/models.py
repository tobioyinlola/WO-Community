from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

SECTION_STATUSES = ("drafted", "needs_input", "edited", "needs_refresh")
PLAN_STATUSES = ("generating", "ready", "failed")


class PlanSectionDef(BaseModel):
    """One of the sections every plan has. Admin managed: wording, inputs and whether it is on."""

    number = models.PositiveSmallIntegerField(unique=True)
    chapter = models.CharField(max_length=80)
    title = models.CharField(max_length=120)
    guidance = models.TextField()  # what a good version of this section covers
    prompt_id = models.CharField(max_length=60, default="plan.section")
    # {"fields": [profile fields it is written from], "outputs": ["forecast"], "facts": [topics]}
    depends_on = models.JSONField(default=dict)
    # Profile fields that must exist before it can be written at all.
    required_inputs = models.JSONField(default=list)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]


class BusinessPlan(BaseModel):
    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="plans"
    )
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=12, default="generating")
    generated_for_profile_version = models.PositiveIntegerField(default=0)
    generated_for_forecast_version = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["venture", "version"], name="tk_plan_version_unique"),
            models.CheckConstraint(
                condition=Q(status__in=PLAN_STATUSES), name="tk_plan_status_valid"
            ),
        ]
        ordering = ["-version"]


class PlanSection(BaseModel):
    plan = models.ForeignKey(BusinessPlan, on_delete=models.CASCADE, related_name="sections")
    definition = models.ForeignKey(PlanSectionDef, on_delete=models.PROTECT, related_name="+")
    number = models.PositiveSmallIntegerField()
    content = models.JSONField(default=dict)  # {"blocks": [...]}
    status = models.CharField(max_length=14, default="needs_input")
    prompts = models.JSONField(default=list)  # gaps the member should fill: [{field, message}]
    version = models.PositiveIntegerField(default=1)
    edited_by_member = models.BooleanField(default=False)
    # The profile and forecast versions the text was written from, so staleness is exact.
    profile_version = models.PositiveIntegerField(default=0)
    forecast_version = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "number"], name="tk_plansection_unique"),
            models.CheckConstraint(
                condition=Q(status__in=SECTION_STATUSES), name="tk_plansection_status_valid"
            ),
        ]
        ordering = ["number"]


class Citation(BaseModel):
    """A numbered reference inside one section, pointing at a source."""

    section = models.ForeignKey(PlanSection, on_delete=models.CASCADE, related_name="citations")
    number = models.PositiveSmallIntegerField()
    source = models.ForeignKey("tk_ai.Source", on_delete=models.PROTECT, related_name="+")
    claim_text = models.CharField(max_length=600)
    position_ref = models.CharField(max_length=40, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["section", "number"], name="tk_citation_unique")
        ]
        ordering = ["number"]


class PlanVersion(BaseModel):
    """A saved copy of a whole plan's text, so a member can go back."""

    plan = models.ForeignKey(BusinessPlan, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    label = models.CharField(max_length=80, blank=True)
    snapshot = models.JSONField(default=list)  # [{number, content, status, prompts}]

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["plan", "version"], name="tk_planversion_unique")
        ]
        ordering = ["-version"]
