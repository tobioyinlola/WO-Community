from django.apps import AppConfig


class UploadsConfig(AppConfig):
    name = "apps.uploads"
    label = "uploads"

    def ready(self) -> None:
        from apps.core import outbox
        from apps.uploads import events, tasks  # noqa: F401

        # Image checks are CPU heavy and talk to the scanner, so they run on the media queue.
        outbox.register_handler(events.UploadConfirmed.topic, "uploads.process_upload", "media")
