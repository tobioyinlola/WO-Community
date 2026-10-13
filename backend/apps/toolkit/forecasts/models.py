from django.db import models

from apps.core.models import BaseModel


class Forecast(BaseModel):
    """A venture's financial assumptions. Figures are calculated from these on demand."""

    venture = models.OneToOneField(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="+"
    )
    template = models.CharField(max_length=24)
    currency = models.CharField(max_length=3)
    assumptions = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)


class ForecastVersion(BaseModel):
    forecast = models.ForeignKey(Forecast, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    assumptions = models.JSONField(default=dict)
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["forecast", "version"], name="tk_forecastversion_unique"
            )
        ]
        ordering = ["-version"]
