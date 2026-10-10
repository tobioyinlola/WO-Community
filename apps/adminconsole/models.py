from django.db import models

from apps.core.models import BaseModel


class DailyMetric(BaseModel):
    """One number for one day, kept so dashboards never scan raw events.

    ``dimension`` splits a metric (for example members by country: the dimension is the country).
    Counts and ratios are both stored as floats; counts are whole numbers well inside float range.
    Snapshot metrics (current state, such as members by country) are stored against the day they
    were taken.
    """

    day = models.DateField()
    metric = models.CharField(max_length=80)
    dimension = models.CharField(max_length=80, blank=True)
    value = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["day", "metric", "dimension"], name="metric_unique")
        ]
        indexes = [models.Index(fields=["metric", "day"], name="metric_series_idx")]


class DashboardState(models.Model):
    """When the summary tables were last refreshed. There is only ever one row."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    refreshed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="dashboard_state_one")]

    def __str__(self) -> str:
        return "dashboard state"
