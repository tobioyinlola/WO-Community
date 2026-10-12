from django.apps import AppConfig


class PrototypesConfig(AppConfig):
    name = "apps.toolkit.prototypes"
    label = "tk_prototypes"

    def ready(self) -> None:
        from apps.toolkit.prototypes import handlers

        handlers.register()
