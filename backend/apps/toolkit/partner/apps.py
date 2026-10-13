from django.apps import AppConfig


class PartnerConfig(AppConfig):
    name = "apps.toolkit.partner"
    label = "tk_partner"

    def ready(self) -> None:
        from apps.toolkit.partner import handlers, tasks  # noqa: F401

        handlers.register()
