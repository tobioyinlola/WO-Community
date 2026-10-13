from django.apps import AppConfig


class AiConfig(AppConfig):
    name = "apps.toolkit.ai"
    label = "tk_ai"

    def ready(self) -> None:
        from apps.toolkit.ai import handlers

        handlers.register()
