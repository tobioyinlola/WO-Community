import os

from celery import Celery
from celery.signals import worker_process_init

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("wo_community", task_cls="apps.core.celery_base:BaseTask")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_process_init.connect
def _start_tracing(**_: object) -> None:
    from config import telemetry

    telemetry.setup("wo-community-worker")
