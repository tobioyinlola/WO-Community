from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self) -> None:
        from apps.core.logging import configure_logging
        from apps.core.sentry import init_sentry

        configure_logging()
        init_sentry()
