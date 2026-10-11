from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.toolkit.jobs"
    label = "tk_jobs"

    def ready(self) -> None:
        from apps.toolkit.jobs import tasks  # noqa: F401
