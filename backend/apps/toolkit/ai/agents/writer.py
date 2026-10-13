"""The writer: text for fields, sections and slides, only ever from what the venture holds."""

from typing import Any
from uuid import UUID

from rest_framework import exceptions

from apps.core.text import plain
from apps.toolkit.ai import runner, safety
from apps.toolkit.ventures import schema
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.selectors import profile_of

SUGGESTIBLE = {
    "one_liner": 160,
    "startup_idea": 2000,
    "business_concept": 2000,
    "target_customer": 1000,
    "problem": 2000,
    "problem_today": 2000,
    "problem_evidence": 2000,
    "solution": 2000,
    "differentiator": 1000,
    "sales_channel": 500,
}


def suggest_field(*, venture: Venture, owner_id: UUID, field: str, intent: str) -> list[str]:
    """Up to three alternatives for one text field. Nothing is saved: the member picks."""
    if field not in SUGGESTIBLE:
        raise exceptions.ValidationError({"field": ["Suggestions are available for text fields."]})
    screened = safety.screen(intent)
    if screened.blocked:
        raise exceptions.ValidationError({"intent": [screened.reply]})
    limit = SUGGESTIBLE[field]
    answer = runner.structured(
        prompt_id="profile.suggest",
        variables={
            "field": field,
            "intent": plain(intent)[:500] or "write a clear version",
            "max_length": limit,
            "profile": profile_of(venture).fields,
        },
        owner_id=owner_id,
        venture=venture,
    )
    clean: list[str] = []
    for item in answer.get("suggestions", []):
        text = plain(str(item))[:limit]
        if text and text not in clean and not safety.leaks_instructions(text):
            clean.append(text)
    return clean[:3]


def fill_from_text(
    *, venture: Venture, owner_id: UUID, text: str
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Fields a free text paragraph supports. Returns (proposed, rejected); nothing is saved."""
    cleaned = plain(text)
    if len(cleaned) < 20:
        raise exceptions.ValidationError({"text": ["Write at least a sentence or two."]})
    answer = runner.structured(
        prompt_id="profile.fill_from_text",
        variables={"text": cleaned[:5000]},
        owner_id=owner_id,
        venture=venture,
    )
    proposed: dict[str, Any] = {}
    rejected: dict[str, list[str]] = {}
    for name, value in (answer.get("proposed") or {}).items():
        try:
            built = schema.validate_patch({name: value})
        except schema.ProfileInvalid as exc:
            rejected[name] = exc.errors.get(name, ["Not valid."])
            continue
        if built.get(name) is not None:
            proposed[name] = built[name]
    return proposed, rejected
