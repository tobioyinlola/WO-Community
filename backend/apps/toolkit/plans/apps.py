from django.apps import AppConfig


class PlansConfig(AppConfig):
    name = "apps.toolkit.plans"
    label = "tk_plans"

    def ready(self) -> None:
        from apps.toolkit.plans import handlers

        handlers.register()
