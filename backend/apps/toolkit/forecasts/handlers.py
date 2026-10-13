from typing import Any

from apps.toolkit.forecasts import service
from apps.toolkit.jobs import services as jobs
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_forecast(venture: Venture) -> dict[str, Any] | None:
    forecast = service.get(venture)
    if forecast is None:
        return None
    return {
        "version": forecast.version,
        "template": forecast.template,
        "currency": forecast.currency,
        "assumptions": forecast.assumptions,
    }


def register() -> None:
    jobs.register("exports.forecast", service.export_forecast, queue="exports")
    ventures.register_exporter("forecast", export_forecast)
