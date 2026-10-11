from django.apps import AppConfig


class MentorshipConfig(AppConfig):
    name = "apps.mentorship"
    label = "mentorship"

    def ready(self) -> None:
        from django.db import transaction
        from django.db.models.signals import post_delete, post_save

        from apps.mentorship import cache, handlers, tasks  # noqa: F401
        from apps.mentorship.models import MentorProfile

        def changed(**_: object) -> None:
            # Cached recommendations describe mentors, so any change to one makes them stale.
            transaction.on_commit(cache.bump)

        post_save.connect(changed, sender=MentorProfile, weak=False)
        post_delete.connect(changed, sender=MentorProfile, weak=False)
        handlers.register()
