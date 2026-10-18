from django.apps import AppConfig


class FeedConfig(AppConfig):
    name = "apps.feed"
    label = "feed"

    def ready(self) -> None:
        from apps.core import shareables
        from apps.feed import handlers, sharing, tasks  # noqa: F401

        handlers.register()
        shareables.register("post", sharing.post_card)
