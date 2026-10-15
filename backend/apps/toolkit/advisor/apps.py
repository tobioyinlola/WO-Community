from django.apps import AppConfig


class AdvisorConfig(AppConfig):
    name = "apps.toolkit.advisor"
    label = "tk_advisor"

    def ready(self) -> None:
        from apps.toolkit.advisor import handlers

        handlers.register()
