from django.apps import AppConfig


class StartupsConfig(AppConfig):
    name = "apps.startups"
    label = "startups"

    def ready(self) -> None:
        from apps.startups import handlers, tasks  # noqa: F401

        handlers.register()
