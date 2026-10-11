from django.apps import AppConfig


class JobsConfig(AppConfig):
    name = "apps.toolkit.jobs"
    label = "tk_jobs"

    def ready(self) -> None:
        from apps.toolkit.jobs import exports, tasks  # noqa: F401
        from apps.toolkit.ventures import services as ventures

        ventures.register_eraser(exports.erase_for)
