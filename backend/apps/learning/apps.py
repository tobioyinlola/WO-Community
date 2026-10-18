from django.apps import AppConfig


class LearningConfig(AppConfig):
    name = "apps.learning"
    label = "learning"

    def ready(self) -> None:
        from apps.core import shareables
        from apps.learning import categories, handlers, sharing, tasks  # noqa: F401
        from apps.reference import usage

        handlers.register()
        usage.register("course_categories", categories.count_by_category)
        usage.register_rename("course_categories", categories.rename)
        shareables.register("course", sharing.course_card)
