from celery import shared_task

from apps.accounts import membership


@shared_task(name="accounts.purge_rejected")
def purge_rejected() -> int:
    return membership.purge_rejected_registrations()
