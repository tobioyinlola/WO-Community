from django.apps import AppConfig


class SharingConfig(AppConfig):
    name = "apps.toolkit.sharing"
    label = "tk_sharing"

    def ready(self) -> None:
        from apps.toolkit.sharing import handlers

        handlers.register()
