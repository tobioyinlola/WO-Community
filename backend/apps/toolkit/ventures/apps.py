from django.apps import AppConfig


class VenturesConfig(AppConfig):
    name = "apps.toolkit.ventures"
    label = "tk_ventures"

    def ready(self) -> None:
        from apps.toolkit.ventures import tasks  # noqa: F401
