from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "apps.events"
    label = "events"

    def ready(self) -> None:
        from apps.events import handlers, tasks  # noqa: F401

        handlers.register()
