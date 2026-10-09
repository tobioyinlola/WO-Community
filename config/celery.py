import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("wo_community", task_cls="apps.core.celery_base:BaseTask")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
