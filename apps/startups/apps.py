from django.apps import AppConfig


class StartupsConfig(AppConfig):
    name = "apps.startups"
    label = "startups"

    def ready(self) -> None:
        from apps.startups import handlers, tasks  # noqa: F401

        handlers.register()

        from apps.reference import usage
        from apps.startups import selectors

        usage.register("sectors", selectors.count_by_sector)
        usage.register("stages", selectors.count_by_stage)
