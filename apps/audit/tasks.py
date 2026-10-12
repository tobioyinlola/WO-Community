from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.audit import partitions, services


@shared_task(name="audit.ensure_partitions")
def ensure_partitions() -> list[str]:
    return partitions.ensure_month_partitions(timezone.now().date(), months_ahead=3)


@shared_task(name="audit.verify_previous_day")
def verify_previous_day() -> bool:
    yesterday = timezone.now().date() - timedelta(days=1)
    return services.verify_day(yesterday)
