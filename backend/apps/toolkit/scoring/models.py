from django.db import models

from apps.core.models import BaseModel


class ScoreRubric(BaseModel):
    """How a venture is scored: dimensions, weights and thresholds. Admin managed, versioned.

    Changing a rubric means adding a new version and activating it; old assessments keep the
    version they were scored with, so their numbers stay explainable.
    """

    version = models.PositiveIntegerField(unique=True)
    active = models.BooleanField(default=False)
    notes = models.CharField(max_length=300, blank=True)
    config = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["active"], condition=models.Q(active=True), name="tk_rubric_one_active"
            )
        ]


class Assessment(BaseModel):
    """One scored report for a venture at a point in time."""

    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="assessments"
    )
    rubric_version = models.PositiveIntegerField()
    profile_version = models.PositiveIntegerField()
    overall_score = models.PositiveSmallIntegerField(null=True, blank=True)
    verdict = models.CharField(max_length=80)
    # [{key, label, weight, score|null, status: scored|insufficient_data, evidence[], explanation}]
    dimensions = models.JSONField(default=list)
    strengths = models.JSONField(default=list)
    gaps = models.JSONField(default=list)
    next_actions = models.JSONField(default=list)
    explanation = models.TextField(blank=True)  # how the score was worked out, in plain words
    scored_weight = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["venture", "-created_at"], name="tk_assessment_venture_idx")
        ]
        ordering = ["-created_at"]
