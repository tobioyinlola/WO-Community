from django.apps import AppConfig


class FeedConfig(AppConfig):
    name = "apps.feed"
    label = "feed"

    def ready(self) -> None:
        from apps.feed import handlers, tasks  # noqa: F401

        handlers.register()
