from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.analytics import partitions
from apps.analytics.models import PartitionArchive


@shared_task(name="analytics.ensure_partitions")
def ensure_partitions() -> list[str]:
    return partitions.ensure_month_partitions(timezone.now().date(), months_ahead=3)


@shared_task(name="analytics.drop_expired")
def drop_expired() -> list[str]:
    archived = None
    if settings.ANALYTICS_REQUIRE_ARCHIVE:
        archived = set(PartitionArchive.objects.values_list("partition", flat=True))
    return partitions.drop_expired_partitions(
        timezone.now(), settings.ANALYTICS_RETENTION_MONTHS, archived=archived
    )
