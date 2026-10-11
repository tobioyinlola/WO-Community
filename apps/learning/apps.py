from django.apps import AppConfig


class LearningConfig(AppConfig):
    name = "apps.learning"
    label = "learning"

    def ready(self) -> None:
        from apps.learning import handlers, tasks  # noqa: F401

        handlers.register()
