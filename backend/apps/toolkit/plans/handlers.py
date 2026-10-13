from typing import Any

from apps.toolkit.jobs import services as jobs
from apps.toolkit.plans import selectors, service
from apps.toolkit.ventures import services as ventures
from apps.toolkit.ventures.models import Venture


def export_plan(venture: Venture) -> dict[str, Any] | None:
    plan = service.latest(venture)
    if plan is None:
        return None
    return {
        "version": plan.version,
        "status": plan.status,
        "sections": [
            {
                "number": s.number,
                "title": s.definition.title,
                "status": s.status,
                "content": s.content,
                "citations": selectors.citations_of(s),
            }
            for s in plan.sections.select_related("definition").order_by("number")
        ],
    }


def register() -> None:
    jobs.register("plan.generate", service.generate)
    jobs.register("exports.plan", service.export_plan, queue="exports")
    ventures.register_exporter("plan", export_plan)
