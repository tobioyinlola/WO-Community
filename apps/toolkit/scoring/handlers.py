from typing import Any

from apps.toolkit.jobs import services as jobs
from apps.toolkit.scoring import selectors, service
from apps.toolkit.scoring.models import Assessment
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_scores(venture: Venture) -> list[dict[str, Any]]:
    return [
        {**selectors.view(a), "id": str(a.pk), "created_at": a.created_at.isoformat()}
        for a in Assessment.objects.filter(venture=venture).order_by("created_at")
    ]


def register() -> None:
    jobs.register("score.generate", service.generate)
    ventures.register_exporter("scores", export_scores)
