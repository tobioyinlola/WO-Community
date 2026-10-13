from django.apps import AppConfig


class EditorialConfig(AppConfig):
    name = "apps.editorial"
    label = "editorial"

    def ready(self) -> None:
        from apps.editorial import handlers, tasks  # noqa: F401

        handlers.register()
