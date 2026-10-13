from celery import shared_task

from apps.toolkit.partner import service


@shared_task(name="toolkit.weekly_nudges")
def weekly_nudges() -> int:
    return service.weekly_nudges()
