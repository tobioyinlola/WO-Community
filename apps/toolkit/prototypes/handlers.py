from typing import Any

from apps.toolkit.jobs import services as jobs
from apps.toolkit.prototypes import service
from apps.toolkit.prototypes.models import Prototype
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_prototypes(venture: Venture) -> list[dict[str, Any]]:
    return [
        {"id": str(p.pk), "title": p.title, "version": p.version, "spec": p.spec}
        for p in Prototype.objects.filter(venture=venture)
    ]


def register() -> None:
    jobs.register("prototype.generate", service.generate)
    ventures.register_exporter("prototypes", export_prototypes)
