from celery import shared_task

from apps.core import outbox


@shared_task(name="core.dispatch_outbox")
def dispatch_outbox() -> int:
    return outbox.dispatch_pending()
