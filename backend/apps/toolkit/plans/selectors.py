from typing import Any

from apps.toolkit.plans import content, service
from apps.toolkit.plans.models import BusinessPlan, PlanSection
from apps.toolkit.ventures.models import Venture


def citations_of(section: PlanSection) -> list[dict[str, Any]]:
    return [
        {
            "number": c.number,
            "claim_text": c.claim_text,
            "source_name": c.source.publisher or c.source.title,
            "url": c.source.url,
            "date": c.source.retrieved_at.date().isoformat(),
        }
        for c in section.citations.select_related("source")
    ]


def section_view(venture: Venture, section: PlanSection, *, full: bool = True) -> dict[str, Any]:
    stale = service.stale_fields(venture, section)
    data: dict[str, Any] = {
        "number": section.number,
        "chapter": section.definition.chapter,
        "title": section.definition.title,
        "status": section.status,
        "stale": bool(stale),
        "stale_fields": stale,
        "prompts": section.prompts,
        "version": section.version,
        "edited_by_member": section.edited_by_member,
        "word_count": content.word_count(section.content),
        "updated_at": section.updated_at,
    }
    if full:
        data["guidance"] = section.definition.guidance
        data["content"] = section.content
        data["citations"] = citations_of(section)
    return data


def plan_view(venture: Venture, plan: BusinessPlan) -> dict[str, Any]:
    sections = plan.sections.select_related("definition").order_by("number")
    return {
        "id": plan.pk,
        "version": plan.version,
        "status": plan.status,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "sections": [section_view(venture, s, full=False) for s in sections],
    }


def versions(plan: BusinessPlan) -> list[dict[str, Any]]:
    return [
        {"version": v.version, "label": v.label, "created_at": v.created_at}
        for v in plan.versions.order_by("-version")
    ]
