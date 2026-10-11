"""What a deck may contain, and the only way to change it.

A deck is data: slides made of a small set of element types, every string plain text. There is no
HTML, no script, no styling beyond a named palette and font, and no link whose address the member
typed. Images are references to files the platform re-encoded. Anything not on the lists below is
refused, so a deck is always safe to show, export and share.
"""

import copy
import re
import secrets
from typing import Any

from django.conf import settings

from apps.core.text import plain

LAYOUTS = (
    "title",
    "statement",
    "bullets",
    "two_column",
    "metrics",
    "table",
    "image",
    "quote",
    "team",
    "closing",
)
ELEMENT_TYPES = ("heading", "text", "bullets", "metric", "table", "image", "linked")
PALETTES = {
    "light": {"background": "FFFFFF", "text": "1F2937", "accent": "2563EB", "muted": "6B7280"},
    "dark": {"background": "111827", "text": "F9FAFB", "accent": "60A5FA", "muted": "9CA3AF"},
    "warm": {"background": "FFF7ED", "text": "431407", "accent": "EA580C", "muted": "9A3412"},
    "forest": {"background": "F0FDF4", "text": "14532D", "accent": "16A34A", "muted": "4D7C0F"},
}
FONTS = ("sans", "serif")
ACCENT = re.compile(r"^#[0-9A-Fa-f]{6}$")

# What a linked element may point at.
PROFILE_FIELDS = (
    "name",
    "one_liner",
    "problem",
    "solution",
    "startup_idea",
    "target_customer",
    "differentiator",
    "sales_channel",
    "country",
    "city",
    "stage",
)
FORECAST_METRICS = (
    "revenue_year1",
    "revenue_year2",
    "net_income_year1",
    "net_income_year2",
    "gross_margin_pct_year1",
    "break_even_month",
    "lowest_cash",
    "extra_funding_needed",
    "total_funding",
    "annual_run_rate",
)
SERIES = ("revenue", "cash")
LINK_KINDS = ("profile_field", "forecast_metric", "forecast_series", "team", "competitors")

LIMITS = {
    "title": 120,
    "heading": 120,
    "text": 700,
    "bullet": 220,
    "bullets": 8,
    "metric_label": 40,
    "metric_value": 40,
    "metric_note": 100,
    "columns": 6,
    "rows": 10,
    "cell": 80,
    "notes": 1000,
    "alt": 200,
}


class InvalidDeck(Exception):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def _text(value: Any, path: str, limit: int, *, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InvalidDeck(path, "Must be text.")
    cleaned = plain(value).strip()
    if len(cleaned) > limit:
        raise InvalidDeck(path, f"Too long ({limit} characters at most).")
    if required and not cleaned:
        raise InvalidDeck(path, "Required.")
    return cleaned


def _id(value: Any, path: str, used: set[str]) -> str:
    if isinstance(value, str) and re.fullmatch(r"[a-z0-9]{1,16}", value) and value not in used:
        used.add(value)
        return value
    if value not in (None, ""):
        raise InvalidDeck(path, "An id is 1 to 16 lowercase letters or digits and must be unique.")
    while True:
        candidate = secrets.token_hex(5)  # new ids are random, so they never meet a later one
        if candidate not in used:
            used.add(candidate)
            return candidate


def _element(el: Any, path: str, ids: set[str], assets: set[str]) -> dict:
    if not isinstance(el, dict) or el.get("type") not in ELEMENT_TYPES:
        raise InvalidDeck(path, "type must be one of " + ", ".join(ELEMENT_TYPES) + ".")
    kind = el["type"]
    out: dict[str, Any] = {"id": _id(el.get("id"), f"{path}/id", ids), "type": kind}
    source = el.get("source")
    if isinstance(source, str) and re.fullmatch(r"[a-z_]{1,40}(\.[a-z_]{1,40})?", source):
        out["source"] = source  # which profile field this was filled from
    if kind in ("heading", "text"):
        out["text"] = _text(el.get("text"), f"{path}/text", LIMITS[kind])
    elif kind == "bullets":
        items = el.get("items")
        if not isinstance(items, list) or len(items) > LIMITS["bullets"]:
            raise InvalidDeck(f"{path}/items", f"At most {LIMITS['bullets']} bullets.")
        cleaned = [_text(i, f"{path}/items", LIMITS["bullet"]) for i in items]
        out["items"] = [i for i in cleaned if i]
    elif kind == "metric":
        out["label"] = _text(el.get("label"), f"{path}/label", LIMITS["metric_label"])
        out["value"] = _text(el.get("value"), f"{path}/value", LIMITS["metric_value"])
        out["note"] = _text(el.get("note"), f"{path}/note", LIMITS["metric_note"])
    elif kind == "table":
        columns, rows = el.get("columns"), el.get("rows")
        if not isinstance(columns, list) or not 1 <= len(columns) <= LIMITS["columns"]:
            raise InvalidDeck(f"{path}/columns", f"1 to {LIMITS['columns']} columns.")
        if not isinstance(rows, list) or len(rows) > LIMITS["rows"]:
            raise InvalidDeck(f"{path}/rows", f"At most {LIMITS['rows']} rows.")
        cols = [_text(c, f"{path}/columns", LIMITS["cell"]) for c in columns]
        body = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(cols):
                raise InvalidDeck(f"{path}/rows", f"Every row needs {len(cols)} cells.")
            body.append([_text(c, f"{path}/rows", LIMITS["cell"]) for c in row])
        out["columns"], out["rows"] = cols, body
    elif kind == "image":
        asset = el.get("asset_id")
        if not isinstance(asset, str) or asset not in assets:
            raise InvalidDeck(f"{path}/asset_id", "Use an image uploaded to this deck.")
        out["asset_id"] = asset
        out["alt"] = _text(el.get("alt"), f"{path}/alt", LIMITS["alt"], required=True)
    else:  # linked
        link = el.get("kind")
        if link not in LINK_KINDS:
            raise InvalidDeck(f"{path}/kind", "Not a known link: " + ", ".join(LINK_KINDS) + ".")
        out["kind"] = link
        if link == "profile_field":
            if el.get("ref") not in PROFILE_FIELDS:
                raise InvalidDeck(f"{path}/ref", "Not a profile field you can show.")
            out["ref"] = el["ref"]
        elif link == "forecast_metric":
            if el.get("ref") not in FORECAST_METRICS:
                raise InvalidDeck(f"{path}/ref", "Not a forecast figure you can show.")
            out["ref"] = el["ref"]
            out["label"] = _text(el.get("label"), f"{path}/label", LIMITS["metric_label"])
        elif link == "forecast_series":
            if el.get("ref") not in SERIES:
                raise InvalidDeck(f"{path}/ref", "Choose revenue or cash.")
            out["ref"] = el["ref"]
            out["label"] = _text(el.get("label"), f"{path}/label", LIMITS["metric_label"])
    return out


def clean(content: Any, *, assets: set[str] | None = None) -> dict[str, Any]:
    """The validated, cleaned deck content, or ``InvalidDeck`` naming the first problem."""
    asset_ids = assets or set()
    if not isinstance(content, dict) or not isinstance(content.get("slides"), list):
        raise InvalidDeck("/slides", "A deck has a list of slides.")
    slides_in = content["slides"]
    if len(slides_in) > settings.DECK_MAX_SLIDES:
        raise InvalidDeck("/slides", f"At most {settings.DECK_MAX_SLIDES} slides.")
    slide_ids: set[str] = set()
    slides: list[dict[str, Any]] = []
    for i, slide in enumerate(slides_in):
        path = f"/slides/{i}"
        if not isinstance(slide, dict) or slide.get("layout") not in LAYOUTS:
            raise InvalidDeck(f"{path}/layout", "Choose one of: " + ", ".join(LAYOUTS) + ".")
        elements = slide.get("elements") or []
        if not isinstance(elements, list) or len(elements) > settings.DECK_MAX_ELEMENTS_PER_SLIDE:
            raise InvalidDeck(
                f"{path}/elements",
                f"At most {settings.DECK_MAX_ELEMENTS_PER_SLIDE} elements on a slide.",
            )
        element_ids: set[str] = set()
        slides.append(
            {
                "id": _id(slide.get("id"), f"{path}/id", slide_ids),
                "layout": slide["layout"],
                "title": _text(slide.get("title"), f"{path}/title", LIMITS["title"]),
                "notes": _text(slide.get("notes"), f"{path}/notes", LIMITS["notes"]),
                "elements": [
                    _element(e, f"{path}/elements/{j}", element_ids, asset_ids)
                    for j, e in enumerate(elements)
                ],
            }
        )
    return {"slides": slides, "theme": clean_theme(content.get("theme"))}


def clean_theme(theme: Any) -> dict[str, str]:
    theme = theme or {}
    if not isinstance(theme, dict):
        raise InvalidDeck("/theme", "Must be an object.")
    palette = theme.get("palette", "light")
    font = theme.get("font", "sans")
    if palette not in PALETTES:
        raise InvalidDeck("/theme/palette", "Choose one of: " + ", ".join(PALETTES) + ".")
    if font not in FONTS:
        raise InvalidDeck("/theme/font", "Choose one of: " + ", ".join(FONTS) + ".")
    out = {"palette": palette, "font": font}
    accent = theme.get("accent")
    if accent:
        if not isinstance(accent, str) or not ACCENT.match(accent):
            raise InvalidDeck("/theme/accent", "Use a colour like #1D4ED8.")
        out["accent"] = accent.upper()
    return out


# --- JSON patch, the subset a deck editor needs ----------------------------------------------


class PatchError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _walk(doc: Any, parts: list[str]) -> tuple[Any, str]:
    node = doc
    for part in parts[:-1]:
        node = _step(node, part)
    return node, parts[-1]


def _step(node: Any, part: str) -> Any:
    if isinstance(node, list):
        if not part.isdigit() or int(part) >= len(node):
            raise PatchError(f"No item {part}.")
        return node[int(part)]
    if isinstance(node, dict):
        if part not in node:
            raise PatchError(f"No {part}.")
        return node[part]
    raise PatchError(f"Cannot go into {part}.")


def _split(path: Any) -> list[str]:
    if not isinstance(path, str) or not path.startswith("/"):
        raise PatchError("A path starts with a slash.")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:]]
    if not parts or parts[0] not in ("slides", "theme"):
        raise PatchError("Only /slides and /theme can be changed.")
    return parts


def apply_patch(content: dict[str, Any], ops: Any) -> dict[str, Any]:
    """Apply add, remove, replace and move operations to a copy of the content."""
    if not isinstance(ops, list) or not 1 <= len(ops) <= 200:
        raise PatchError("Send between 1 and 200 operations.")
    doc = copy.deepcopy(content)
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in ("add", "remove", "replace", "move"):
            raise PatchError("Each operation is add, remove, replace or move.")
        kind = op["op"]
        parts = _split(op.get("path"))
        if kind == "move":
            source = _split(op.get("from"))
            holder, key = _walk(doc, source)
            value = _step(holder, key)
            if isinstance(holder, list):
                holder.pop(int(key))
            else:
                del holder[key]
            kind, payload = "add", value
        else:
            payload = op.get("value")
        holder, key = _walk(doc, parts)
        if kind == "remove":
            if isinstance(holder, list) and key.isdigit() and int(key) < len(holder):
                holder.pop(int(key))
            elif isinstance(holder, dict) and key in holder:
                del holder[key]
            else:
                raise PatchError("Nothing to remove there.")
        elif kind == "replace":
            if isinstance(holder, list) and key.isdigit() and int(key) < len(holder):
                holder[int(key)] = payload
            elif isinstance(holder, dict) and key in holder:
                holder[key] = payload
            else:
                raise PatchError("Nothing to replace there.")
        else:  # add
            if isinstance(holder, list):
                if key == "-":
                    holder.append(payload)
                elif key.isdigit() and int(key) <= len(holder):
                    holder.insert(int(key), payload)
                else:
                    raise PatchError("Bad position.")
            elif isinstance(holder, dict):
                holder[key] = payload
            else:
                raise PatchError("Cannot add there.")
    return doc
