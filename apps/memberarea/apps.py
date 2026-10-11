from django.apps import AppConfig


class MemberAreaConfig(AppConfig):
    name = "apps.memberarea"
    label = "memberarea"

    def ready(self) -> None:
        from apps.memberarea import handlers, tasks  # noqa: F401

        handlers.register()
