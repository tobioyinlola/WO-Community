from django.apps import AppConfig


class ScoringConfig(AppConfig):
    name = "apps.toolkit.scoring"
    label = "tk_scoring"

    def ready(self) -> None:
        from apps.toolkit.scoring import handlers

        handlers.register()
