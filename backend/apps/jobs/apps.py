from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.jobs"
    label = "jobs"

    def ready(self) -> None:
        from apps.jobs import handlers, tasks  # noqa: F401

        handlers.register()
