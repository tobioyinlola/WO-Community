from celery import shared_task

from apps.toolkit.ventures import services


@shared_task(name="toolkit.erase_deleted_ventures")
def erase_deleted_ventures() -> int:
    return services.erase_due()
