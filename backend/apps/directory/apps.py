from django.apps import AppConfig


class DirectoryConfig(AppConfig):
    name = "apps.directory"
    label = "directory"

    def ready(self) -> None:
        from apps.directory import handlers, tasks  # noqa: F401

        handlers.register()
