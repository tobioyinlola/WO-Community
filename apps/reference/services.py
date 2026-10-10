"""Managing the sector, stage and skill lists.

Slugs are fixed once created because they appear in URLs, filters and stored
records. Names, order and the active flag can change. An entry in use is
retired (hidden from new choices) rather than deleted.
"""

import re
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.db.models.functions import Lower
from django.utils.text import slugify
from rest_framework import exceptions

from apps.core import events as domain_events
from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.reference import events, usage
from apps.reference.models import ReferenceItem, Sector, Skill, Stage

# Typed loosely: the three models share ReferenceItem, which is abstract and has no manager.
KINDS: dict[str, Any] = {"sectors": Sector, "stages": Stage, "skills": Skill}
MAX_ITEMS = 200
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def model_for(kind: str) -> Any:
    try:
        return KINDS[kind]
    except KeyError as exc:
        raise exceptions.NotFound() from exc


def snapshot(item: ReferenceItem) -> dict[str, Any]:
    """The fields worth recording in the audit log."""
    return {
        "slug": item.slug,
        "name": item.name,
        "active": item.active,
        "sort_order": item.sort_order,
    }


def list_items(kind: str) -> list[dict[str, Any]]:
    """Every entry including retired ones, in display order, with how many records use it."""
    items = list(model_for(kind).objects.order_by("sort_order", "name"))
    totals = usage.counts(kind, [item.slug for item in items])
    return [{**snapshot(item), "id": item.pk, "usage": totals.get(item.slug, 0)} for item in items]


def _clean_name(name: str) -> str:
    cleaned = plain(name)
    if not 2 <= len(cleaned) <= 80:
        raise exceptions.ValidationError({"name": ["Use between 2 and 80 characters."]})
    return cleaned


def _name_taken(model: Any, name: str, exclude: UUID | None = None) -> bool:
    found = model.objects.annotate(lowered=Lower("name")).filter(lowered=name.lower())
    return found.exclude(pk=exclude).exists() if exclude else found.exists()


def create_item(*, kind: str, name: str, slug: str = "", sort_order: int | None = None) -> Any:
    model = model_for(kind)
    name = _clean_name(name)
    slug = slug or slugify(name)[:80]
    if not SLUG_PATTERN.match(slug) or len(slug) > 80:
        raise exceptions.ValidationError(
            {"slug": ["Use lower case letters, numbers and single hyphens."]}
        )
    if model.objects.count() >= MAX_ITEMS:
        raise ConflictError(f"A list can hold at most {MAX_ITEMS} entries.", code="list_full")
    if _name_taken(model, name):
        raise ConflictError("An entry with this name already exists.", code="name_taken")
    if sort_order is None:
        sort_order = (model.objects.aggregate(top=Max("sort_order"))["top"] or 0) + 1
    try:
        with transaction.atomic():
            item = model.objects.create(name=name, slug=slug, sort_order=sort_order)
            domain_events.publish(events.ReferenceChanged(kind=kind, slug=item.slug))
    except IntegrityError as exc:
        raise ConflictError("An entry with this slug already exists.", code="slug_taken") from exc
    return item


def update_item(
    *,
    kind: str,
    item_id: UUID,
    name: str | None = None,
    active: bool | None = None,
    sort_order: int | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Change an entry. Returns it with its previous values for the audit record."""
    model = model_for(kind)
    with transaction.atomic():
        item = model.objects.select_for_update().filter(pk=item_id).first()
        if item is None:
            raise exceptions.NotFound()
        before = snapshot(item)
        if name is not None:
            cleaned = _clean_name(name)
            if _name_taken(model, cleaned, exclude=item.pk):
                raise ConflictError("An entry with this name already exists.", code="name_taken")
            item.name = cleaned
        if active is not None:
            item.active = active
        if sort_order is not None:
            item.sort_order = sort_order
        item.save()
        domain_events.publish(events.ReferenceChanged(kind=kind, slug=item.slug))
    return item, before


def delete_item(*, kind: str, item_id: UUID) -> dict[str, Any]:
    """Remove an unused entry (a typo, say). Anything in use must be retired instead."""
    model = model_for(kind)
    with transaction.atomic():
        item = model.objects.select_for_update().filter(pk=item_id).first()
        if item is None:
            raise exceptions.NotFound()
        in_use = usage.counts(kind, [item.slug])[item.slug]
        if in_use:
            raise ConflictError(
                f"{in_use} record(s) use this entry. Deactivate it instead.", code="in_use"
            )
        before = snapshot(item)
        item.delete()  # a database level PROTECT is the last line of defence
        domain_events.publish(events.ReferenceChanged(kind=kind, slug=before["slug"]))
    return before


def reorder(*, kind: str, ids: list[UUID]) -> list[dict[str, Any]]:
    """Set the display order. ``ids`` must name every entry exactly once."""
    model = model_for(kind)
    if len(set(ids)) != len(ids):
        raise exceptions.ValidationError({"ids": ["Each entry may appear only once."]})
    with transaction.atomic():
        items = {item.pk: item for item in model.objects.select_for_update()}
        if set(items) != set(ids):
            raise ConflictError(
                "The list changed. Reload it and send every entry.", code="list_changed"
            )
        for position, item_id in enumerate(ids, start=1):
            if items[item_id].sort_order != position:
                items[item_id].sort_order = position
                items[item_id].save(update_fields=["sort_order", "updated_at"])
        domain_events.publish(events.ReferenceChanged(kind=kind, slug=""))
    return list_items(kind)
