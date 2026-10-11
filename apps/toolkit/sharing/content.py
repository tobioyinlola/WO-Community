"""What a share link shows. Read only, and never more than the owner would put on a page.

Speaker notes, profile fields, plan sections still waiting for input and anything member private
are left out. Each kind is built from the same services the owner's own screens use, so a shared
view cannot show numbers the owner does not see.
"""

from typing import Any
from uuid import UUID

from django.http import Http404

from apps.toolkit.decks import service as decks
from apps.toolkit.plans import selectors as plan_selectors
from apps.toolkit.plans import service as plans
from apps.toolkit.scoring import selectors as score_selectors
from apps.toolkit.sharing.models import ShareLink
from apps.toolkit.ventures.models import Venture


def subject_exists(venture: Venture, subject_type: str, subject_id: UUID) -> bool:
    if subject_type == "deck":
        return decks.get(venture, subject_id) is not None
    if subject_type == "plan_summary":
        return plans.latest(venture) is not None and subject_id == venture.pk
    if subject_type == "score_summary":
        return score_selectors.latest(venture) is not None and subject_id == venture.pk
    return False


def build(link: ShareLink) -> dict[str, Any]:
    venture = link.venture
    if link.subject_type == "deck":
        deck = decks.get(venture, link.subject_id)
        if deck is None:
            raise Http404
        shown = decks.resolve(venture, deck)
        slides = [{k: v for k, v in s.items() if k != "notes"} for s in shown["slides"]]
        return {
            "type": "deck",
            "title": deck.title,
            "venture_name": venture.name,
            "slides": slides,
            "theme": shown["theme"],
        }
    if link.subject_type == "plan_summary":
        plan = plans.latest(venture)
        if plan is None:
            raise Http404
        sections = []
        for s in plan.sections.select_related("definition").order_by("number"):
            if not s.content.get("blocks"):
                continue
            sections.append(
                {
                    "number": s.number,
                    "chapter": s.definition.chapter,
                    "title": s.definition.title,
                    "content": s.content,
                    "citations": plan_selectors.citations_of(s),
                }
            )
        return {
            "type": "plan_summary",
            "title": f"{venture.name}: business plan",
            "venture_name": venture.name,
            "sections": sections,
        }
    assessment = score_selectors.latest(venture)
    if assessment is None:
        raise Http404
    return {
        "type": "score_summary",
        "title": f"{venture.name}: validation score",
        **score_selectors.summary(venture, assessment),
    }
