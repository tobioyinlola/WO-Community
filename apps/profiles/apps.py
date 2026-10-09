from django.apps import AppConfig


class ProfilesConfig(AppConfig):
    name = "apps.profiles"
    label = "profiles"

    def ready(self) -> None:
        from apps.profiles import handlers, tasks  # noqa: F401

        handlers.register()
