from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    name = "apps.analytics"
    label = "analytics"

    def ready(self) -> None:
        from apps.analytics import tasks  # noqa: F401
