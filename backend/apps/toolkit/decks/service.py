"""Decks: created from the venture, edited by patch, shown with live figures, checked, exported.

Text in a deck is the founder's own, copied from their profile and then theirs to edit. Figures
come from the forecast through linked elements that are looked up each time the deck is shown, so
a number on a slide cannot drift from the forecast. A model may propose wording for one slide; it
saves nothing.
"""

import json
import re
import secrets
from datetime import timedelta
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.integrations.malware import get_scanner
from apps.integrations.storage import get_storage
from apps.integrations.storage.base import PRIVATE
from apps.toolkit.ai import runner, safety
from apps.toolkit.decks import catalog, schema
from apps.toolkit.decks.models import Deck, DeckAsset, DeckTemplate, DeckVersion
from apps.toolkit.forecasts import selectors as forecasts
from apps.toolkit.jobs import exports
from apps.toolkit.jobs.services import JobContext, JobFailed
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.selectors import profile_of
from apps.uploads import images

logger = structlog.get_logger(__name__)

MAX_DECKS = 20
MAX_ASSETS = 40
MAX_ASSET_BYTES = 5_000_000
SNAPSHOT_EVERY = timedelta(minutes=5)
REVENUE_MODEL_NAMES = {
    "subscription": "Subscriptions",
    "transaction_fee": "Transaction fees",
    "marketplace_commission": "Marketplace commission",
    "product_sales": "Product sales",
    "services": "Services",
    "licensing": "Licensing",
    "advertising": "Advertising",
    "other": "Other income",
}
ASSIST_ACTIONS = ("shorten", "punchier", "simplify")


# --- templates -------------------------------------------------------------------------------


def ensure_templates() -> None:
    have = set(DeckTemplate.objects.values_list("slug", flat=True))
    DeckTemplate.objects.bulk_create(
        DeckTemplate(position=i, **row)
        for i, row in enumerate(catalog.TEMPLATES)
        if row["slug"] not in have
    )


def templates() -> list[DeckTemplate]:
    ensure_templates()
    return list(DeckTemplate.objects.filter(active=True))


# --- building a deck from the venture -------------------------------------------------------


def _trim(text: str, limit: int) -> str:
    text = plain(text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: stop + 1] if stop > limit // 2 else cut[: limit - 1].rstrip() + "…"


def _fill_text(name: str, fields: dict[str, Any]) -> str:
    value = fields.get(name)
    if name == "estimated_customers" and value:
        return f"About {int(value):,} potential customers"
    if value in (None, "", [], {}):
        return ""
    return _trim(str(value), schema.LIMITS["text"])


def _fill_bullets(name: str, fields: dict[str, Any]) -> list[str]:
    if name == "use_of_funds":
        values = (fields.get("funding") or {}).get("use_of_funds", [])
    elif name == "revenue_models":
        values = [REVENUE_MODEL_NAMES.get(m, m) for m in fields.get("revenue_models", [])]
    else:
        values = fields.get(name) or []
    return [_trim(str(v), schema.LIMITS["bullet"]) for v in values][: schema.LIMITS["bullets"]]


def _metric_value(path: str, fields: dict[str, Any]) -> str:
    head, _, tail = path.partition(".")
    group: dict[str, Any] = fields.get(head) or {}
    value = group.get(tail)
    if value in (None, ""):
        return ""
    number = int(str(value))
    if tail == "revenue_minor":
        return f"{group.get('currency') or ''} {number / 100:,.0f}".strip()
    return f"{number:,}"


def _build_element(spec: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any] | None:
    kind = spec["type"]
    if kind == "heading":
        return {"type": "heading", "text": spec["text"]}
    if kind == "text":
        name = spec["fill"]
        return {"type": "text", "text": _fill_text(name, fields), "source": name}
    if kind == "bullets":
        name = spec["fill"]
        return {"type": "bullets", "items": _fill_bullets(name, fields), "source": name}
    if kind == "metric":
        value = _metric_value(spec["fill"], fields)
        if not value:
            return None
        return {"type": "metric", "label": spec["label"], "value": value, "note": ""}
    return {k: v for k, v in spec.items() if k != "fill"}


def build_content(template: DeckTemplate, fields: dict[str, Any]) -> dict[str, Any]:
    slides = []
    for spec in template.slides:
        elements = [
            built
            for built in (_build_element(e, fields) for e in spec["elements"])
            if built is not None
        ]
        slides.append(
            {"layout": spec["layout"], "title": spec["title"], "notes": "", "elements": elements}
        )
    return schema.clean({"slides": slides, "theme": {"palette": "light", "font": "sans"}})


def create(venture: Venture, *, template_slug: str, title: str = "") -> Deck:
    ensure_templates()
    template = DeckTemplate.objects.filter(slug=template_slug, active=True).first()
    if template is None:
        raise exceptions.ValidationError({"template": ["Choose one of the templates."]})
    if Deck.objects.filter(venture=venture, deleted_at__isnull=True).count() >= MAX_DECKS:
        raise ConflictError(f"A venture can have {MAX_DECKS} decks.", code="limit")
    fields = profile_of(venture).fields
    name = title.strip() or f"{fields.get('name', venture.name)}: {template.name}"
    with transaction.atomic():
        deck = Deck.objects.create(
            venture=venture,
            title=plain(name)[:120],
            template_slug=template.slug,
            content=build_content(template, fields),
        )
        DeckVersion.objects.create(deck=deck, version=1, content=deck.content, label="Created")
    return deck


# --- reading ---------------------------------------------------------------------------------


def get(venture: Venture, deck_id: UUID) -> Deck | None:
    return Deck.objects.filter(pk=deck_id, venture=venture, deleted_at__isnull=True).first()


def _asset_ids(deck: Deck) -> set[str]:
    return {str(i) for i in deck.assets.values_list("pk", flat=True)}


def _display_money(minor: int, currency: str) -> str:
    return f"{currency} {minor / 100:,.0f}"


def _figure(headline: dict[str, Any] | None, ref: str) -> dict[str, Any]:
    if headline is None:
        return {"missing": True, "reason": "Create the forecast to show this figure."}
    value = headline["figures"].get(ref)
    if value is None:
        return {"missing": True, "reason": "The forecast has no value for this."}
    currency = headline["currency"]
    if ref == "break_even_month":
        return {"value": value, "display": f"Month {value}"}
    if ref == "gross_margin_pct_year1":
        return {"value": value, "display": f"{value}%"}
    return {
        "value_minor": value,
        "currency": currency,
        "display": _display_money(int(value), currency),
    }


def resolve(venture: Venture, deck: Deck) -> dict[str, Any]:
    """The deck as it should be shown: linked elements looked up, image addresses signed."""
    fields = profile_of(venture).fields
    headline = forecasts.headline(venture)
    storage = get_storage()
    assets = {str(a.pk): a for a in deck.assets.all()}
    team = [{"name": t.name, "role": t.role, "founder": t.is_founder} for t in venture.team.all()]
    competitors = [{"name": c.name, "note": c.differentiator} for c in venture.competitors.all()]
    out_slides = []
    for slide in deck.content.get("slides", []):
        elements = []
        for el in slide["elements"]:
            el = dict(el)
            if el["type"] == "linked":
                kind = el["kind"]
                if kind == "profile_field":
                    el["resolved"] = {"text": str(fields.get(el["ref"], "") or "")}
                elif kind == "forecast_metric":
                    el["resolved"] = _figure(headline, el["ref"])
                elif kind == "forecast_series":
                    series = forecasts.series(venture, el["ref"])
                    el["resolved"] = series or {
                        "missing": True,
                        "reason": "Create the forecast to show this chart.",
                    }
                elif kind == "team":
                    el["resolved"] = {"members": team}
                else:
                    el["resolved"] = {"competitors": competitors}
            elif el["type"] == "image":
                asset = assets.get(el["asset_id"])
                el["url"] = (
                    storage.presign_get(
                        bucket=PRIVATE,
                        key=asset.storage_key,
                        expires_in=settings.EXPORT_URL_TTL,
                        filename="image.webp",
                        content_type=asset.content_type,
                    )
                    if asset
                    else ""
                )
            elements.append(el)
        out_slides.append({**slide, "elements": elements})
    return {"slides": out_slides, "theme": deck.content.get("theme", {})}


# --- editing ---------------------------------------------------------------------------------


def _snapshot(deck: Deck, label: str = "") -> None:
    last = deck.versions.order_by("-version").first()
    now = timezone.now()
    if label or last is None or now - last.created_at > SNAPSHOT_EVERY:
        DeckVersion.objects.update_or_create(
            deck=deck,
            version=deck.version,
            defaults={"content": deck.content, "label": label[:80]},
        )
    else:  # many quick saves share one snapshot
        last.content = deck.content
        last.save(update_fields=["content", "updated_at"])
    old = deck.versions.order_by("-version").values_list("pk", flat=True)[
        settings.DECK_VERSIONS_KEPT :
    ]
    DeckVersion.objects.filter(pk__in=list(old)).delete()


def apply_ops(deck: Deck, *, ops: Any, base_version: int, label: str = "") -> Deck:
    """Change a deck with patch operations. All or nothing; a stale version is 409."""
    with transaction.atomic():
        locked = Deck.objects.select_for_update().get(pk=deck.pk)
        if locked.version != base_version:
            raise ConflictError("The deck changed elsewhere. Reload and try again.", code="stale")
        try:
            changed = schema.apply_patch(locked.content, ops)
            cleaned = schema.clean(changed, assets=_asset_ids(locked))
        except schema.PatchError as exc:
            raise exceptions.ValidationError({"ops": [exc.message]}) from exc
        except schema.InvalidDeck as exc:
            raise exceptions.ValidationError({exc.path: [exc.message]}) from exc
        locked.content = cleaned
        locked.version += 1
        locked.save()
        _snapshot(locked, label)
    return locked


def rename(deck: Deck, *, title: str | None, status: str | None) -> Deck:
    if title is not None:
        cleaned = plain(title).strip()
        if not 1 <= len(cleaned) <= 120:
            raise exceptions.ValidationError({"title": ["Between 1 and 120 characters."]})
        deck.title = cleaned
    if status is not None:
        if status not in ("draft", "ready"):
            raise exceptions.ValidationError({"status": ["Draft or ready."]})
        deck.status = status
    deck.save()
    return deck


def restore(deck: Deck, version: int) -> Deck:
    row = deck.versions.filter(version=version).first()
    if row is None:
        raise exceptions.NotFound()
    assets = _asset_ids(deck)
    slides = []
    for slide in row.content.get("slides", []):
        kept = [e for e in slide["elements"] if e["type"] != "image" or e.get("asset_id") in assets]
        slides.append({**slide, "elements": kept})
    with transaction.atomic():
        locked = Deck.objects.select_for_update().get(pk=deck.pk)
        _snapshot(locked, f"Before restoring version {version}")
        locked.content = schema.clean({**row.content, "slides": slides}, assets=assets)
        locked.version += 1
        locked.save()
        _snapshot(locked, f"Restored version {version}")
    return locked


def delete(deck: Deck) -> None:
    storage = get_storage()
    for asset in deck.assets.all():
        storage.delete(bucket=PRIVATE, key=asset.storage_key)
    deck.delete()


# --- images ----------------------------------------------------------------------------------


def add_asset(deck: Deck, *, owner_id: UUID, data: bytes, filename: str) -> DeckAsset:
    if len(data) > MAX_ASSET_BYTES:
        raise exceptions.ValidationError({"file": ["Images can be up to 5 MB."]})
    if deck.assets.count() >= MAX_ASSETS:
        raise ConflictError(f"A deck can hold {MAX_ASSETS} images.", code="limit")
    kind = images.sniff(data)
    if kind is None:
        raise exceptions.ValidationError({"file": ["Use a PNG, JPEG or WebP image."]})
    verdict = get_scanner().scan(data)
    if not verdict.clean:
        logger.warning("deck_upload_malware", deck_id=str(deck.pk))
        raise exceptions.ValidationError({"file": ["This file was not accepted."]})
    try:
        processed = images.process(data, kind)
    except images.ImageRejected as exc:
        raise exceptions.ValidationError({"file": ["This is not a usable image."]}) from exc
    key = f"toolkit/decks/{deck.pk}/{secrets.token_hex(16)}.webp"
    get_storage().write(
        bucket=PRIVATE,
        key=key,
        data=processed.large,
        content_type="image/webp",
        cache_control="private, no-store",
    )
    return DeckAsset.objects.create(
        deck=deck,
        owner_id=owner_id,
        storage_key=key,
        content_type="image/webp",
        size=len(processed.large),
        width=processed.width,
        height=processed.height,
        filename=plain(filename)[:120],
    )


def remove_asset(deck: Deck, asset: DeckAsset) -> None:
    used = any(
        e.get("type") == "image" and e.get("asset_id") == str(asset.pk)
        for s in deck.content.get("slides", [])
        for e in s["elements"]
    )
    if used:
        raise ConflictError("Remove the image from the slides first.", code="in_use")
    get_storage().delete(bucket=PRIVATE, key=asset.storage_key)
    asset.delete()


def erase_for(venture: Venture) -> None:
    storage = get_storage()
    for asset in DeckAsset.objects.filter(deck__venture=venture):
        storage.delete(bucket=PRIVATE, key=asset.storage_key)


# --- checking and assisting ------------------------------------------------------------------

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _figures(text: str) -> set[str]:
    return {m.replace(",", "").rstrip(".").lstrip("0") or "0" for m in _NUMBER.findall(text)}


def _known_text(venture: Venture) -> str:
    fields = profile_of(venture).fields
    parts = [json.dumps(fields, default=str, ensure_ascii=False)]
    headline = forecasts.headline(venture)
    if headline:
        parts.append(json.dumps(headline, default=str))
    parts.extend(t.name + " " + t.role for t in venture.team.all())
    parts.extend(c.name for c in venture.competitors.all())
    return "\n".join(parts)


def _slide_text(slide: dict[str, Any]) -> str:
    parts = [slide.get("title", "")]
    for el in slide["elements"]:
        if el["type"] in ("heading", "text"):
            parts.append(el.get("text", ""))
        elif el["type"] == "bullets":
            parts.extend(el.get("items", []))
        elif el["type"] == "metric":
            parts.append(f"{el.get('label', '')} {el.get('value', '')} {el.get('note', '')}")
    return "\n".join(p for p in parts if p)


def check(venture: Venture, deck: Deck) -> list[dict[str, Any]]:
    """Things worth fixing before the deck is shown. Advice, never a block."""
    findings: list[dict[str, Any]] = []
    known = _figures(_known_text(venture))
    headline = forecasts.headline(venture)

    def add(slide: int, code: str, severity: str, message: str, element: str = "") -> None:
        findings.append(
            {
                "slide": slide,
                "element": element,
                "code": code,
                "severity": severity,
                "message": message,
            }
        )

    slides = deck.content.get("slides", [])
    if not slides:
        add(0, "empty_deck", "error", "The deck has no slides.")
    if len(slides) > 20:
        add(0, "too_long", "info", f"{len(slides)} slides is long. Most pitches run 10 to 15.")
    for number, slide in enumerate(slides, start=1):
        text = _slide_text(slide)
        label = slide.get("title") or f"Slide {number}"
        for el in slide["elements"]:
            empty_text = el["type"] in ("text", "heading") and not el.get("text", "").strip()
            empty_list = el["type"] == "bullets" and not el.get("items")
            if (empty_text or empty_list) and el.get("source"):
                add(
                    number,
                    "needs_input",
                    "warning",
                    f"{label}: add your {el['source'].replace('_', ' ')} to the profile or "
                    "write it here.",
                    el["id"],
                )
            if el["type"] == "linked" and el["kind"] in ("forecast_metric", "forecast_series"):
                if headline is None:
                    add(
                        number, "no_forecast", "warning", f"{label}: create the forecast.", el["id"]
                    )
            if el["type"] == "image" and not el.get("alt"):
                add(number, "no_alt", "warning", f"{label}: describe the image.", el["id"])
        if len(text) > 600:
            add(number, "dense", "info", f"{label}: a lot of text. Aim for what fits in a glance.")
        if not slide.get("notes") and slide["layout"] not in ("title", "closing"):
            add(number, "no_notes", "info", f"{label}: no speaker notes.")
        unknown = sorted(f for f in _figures(text) - known if not (f.isdigit() and int(f) <= 10))
        if unknown:
            add(
                number,
                "unsupported_figure",
                "warning",
                f"{label}: check {', '.join(unknown)}; it is not in your profile or forecast.",
            )
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["slide"]))
    return findings


def assist(
    *, venture: Venture, owner_id: UUID, deck: Deck, slide_id: str, action: str
) -> dict[str, Any]:
    """Reworded text elements for one slide, as a proposal. Nothing is saved."""
    if action not in ASSIST_ACTIONS:
        raise exceptions.ValidationError({"action": ["Not a known action."]})
    slide = next((s for s in deck.content.get("slides", []) if s["id"] == slide_id), None)
    if slide is None:
        raise exceptions.NotFound()
    current = [e for e in slide["elements"] if e["type"] in ("heading", "text", "bullets")]
    if not current:
        raise exceptions.ValidationError({"slide": ["This slide has no text to work with."]})
    if safety.leaks_instructions(_slide_text(slide)):
        raise exceptions.ValidationError({"slide": ["This slide cannot be reworded."]})
    answer = runner.structured(
        prompt_id="deck.slide",
        variables={
            "action": action,
            "title": slide.get("title", ""),
            "elements": [
                {k: v for k, v in e.items() if k in ("id", "type", "text", "items")}
                for e in current
            ],
            "venture": {"name": profile_of(venture).fields.get("name", "")},
        },
        owner_id=owner_id,
        venture=venture,
    )
    allowed = _figures(_slide_text(slide)) | _figures(_known_text(venture))
    by_id = {e["id"]: e for e in current}
    proposed: list[dict[str, Any]] = []
    removed: set[str] = set()
    for item in answer.get("elements", []):
        original = by_id.get(str(item.get("id")))
        if original is None or item.get("type") != original["type"]:
            continue
        new = {**original}
        if original["type"] == "bullets":
            new["items"] = [
                plain(str(i))[: schema.LIMITS["bullet"]] for i in item.get("items", [])
            ][: schema.LIMITS["bullets"]]
            body = "\n".join(new["items"])
        else:
            new["text"] = plain(str(item.get("text", "")))[: schema.LIMITS[original["type"]]]
            body = new["text"]
        extra = {f for f in _figures(body) - allowed if not (f.isdigit() and int(f) <= 10)}
        if extra:
            removed |= extra
            continue  # a rewrite that adds a figure is dropped, the original stays
        proposed.append(new)
    return {
        "slide_id": slide_id,
        "action": action,
        "elements": proposed,
        "removed": sorted(removed),
    }


# --- export job ------------------------------------------------------------------------------


def export_deck(ctx: JobContext) -> dict[str, Any]:
    """The ``exports.deck`` job. Payload: ``deck_id`` and ``format`` (pptx or pdf)."""
    from apps.toolkit.decks import export

    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    fmt = str(ctx.payload.get("format", "pptx"))
    if fmt not in ("pptx", "pdf"):
        raise JobFailed("bad_format", "Choose pptx or pdf.")
    deck = get(venture, UUID(str(ctx.payload.get("deck_id", ""))))
    if deck is None:
        raise JobFailed("no_deck", "That deck no longer exists.")
    if not deck.content.get("slides"):
        raise JobFailed("empty_deck", "The deck has no slides.")
    ctx.progress(20, "Collecting slides")
    shown = resolve(venture, deck)
    storage = get_storage()
    images_by_id: dict[str, bytes] = {}
    for asset in deck.assets.all():
        try:
            images_by_id[str(asset.pk)] = storage.read(
                bucket=PRIVATE, key=asset.storage_key, max_size=MAX_ASSET_BYTES
            )
        except Exception:
            logger.warning("deck_asset_missing", asset_id=str(asset.pk))
    ctx.progress(50, "Building the file")
    data = (
        export.render_pptx(deck.title, shown, images_by_id)
        if fmt == "pptx"
        else export.render_pdf(deck.title, shown, images_by_id)
    )
    safe = "".join(ch for ch in deck.title if ch.isalnum() or ch in " -_").strip() or "deck"
    file = exports.store(
        venture=venture,
        owner_id=ctx.owner_id,
        kind=f"deck.{fmt}",
        filename=f"{safe}.{fmt}",
        content_type=export.PPTX_TYPE if fmt == "pptx" else export.PDF_TYPE,
        data=data,
    )
    return exports.result_of(file)
