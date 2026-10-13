from django.apps import AppConfig


class ForecastsConfig(AppConfig):
    name = "apps.toolkit.forecasts"
    label = "tk_forecasts"

    def ready(self) -> None:
        from apps.toolkit.forecasts import handlers

        handlers.register()
