from apps.toolkit.forecasts import service
from apps.toolkit.jobs import services as jobs


def register() -> None:
    jobs.register("exports.forecast", service.export_forecast, queue="exports")
