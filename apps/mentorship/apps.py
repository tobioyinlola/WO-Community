from django.apps import AppConfig


class MentorshipConfig(AppConfig):
    name = "apps.mentorship"
    label = "mentorship"

    def ready(self) -> None:
        from apps.mentorship import handlers, tasks  # noqa: F401

        handlers.register()
