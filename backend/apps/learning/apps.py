from django.apps import AppConfig


class LearningConfig(AppConfig):
    name = "apps.learning"
    label = "learning"

    def ready(self) -> None:
        from apps.learning import categories, handlers, tasks  # noqa: F401
        from apps.reference import usage

        handlers.register()
        usage.register("course_categories", categories.count_by_category)
        usage.register_rename("course_categories", categories.rename)
