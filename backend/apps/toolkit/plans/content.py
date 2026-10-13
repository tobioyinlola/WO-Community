"""What a section holds: a short list of plain text blocks, validated and cleaned.

Nothing here is HTML. A block is a paragraph, a bullet list or a small table, and every string is
stripped of markup, so a section can be shown, exported and shared without any risk of script.
"""

import re
from typing import Any

from apps.core.text import plain

MAX_BLOCKS = 40
MAX_TEXT = 4000
MAX_ITEMS = 20
MAX_COLUMNS = 8
MAX_ROWS = 30
BLOCK_TYPES = ("paragraph", "bullets", "table", "heading")


class InvalidContent(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _text(value: Any, where: str, limit: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise InvalidContent(f"{where} must be text.")
    cleaned = plain(value).strip()
    if len(cleaned) > limit:
        raise InvalidContent(f"{where} is too long ({limit} characters at most).")
    return cleaned


def _cites(value: Any, where: str) -> list[int]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or len(value) > 10:
        raise InvalidContent(f"{where}: cites must be a short list of numbers.")
    out: list[int] = []
    for n in value:
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 999:
            raise InvalidContent(f"{where}: cites must be whole numbers.")
        if n not in out:
            out.append(n)
    return out


def clean(content: Any) -> dict[str, Any]:
    """The cleaned ``{"blocks": [...]}`` or ``InvalidContent`` saying what is wrong."""
    if not isinstance(content, dict) or not isinstance(content.get("blocks"), list):
        raise InvalidContent("Content must be an object with a list of blocks.")
    raw = content["blocks"]
    if len(raw) > MAX_BLOCKS:
        raise InvalidContent(f"A section can have at most {MAX_BLOCKS} blocks.")
    blocks: list[dict[str, Any]] = []
    for i, block in enumerate(raw, start=1):
        where = f"Block {i}"
        if not isinstance(block, dict) or block.get("type") not in BLOCK_TYPES:
            raise InvalidContent(f"{where}: type must be one of {', '.join(BLOCK_TYPES)}.")
        kind = block["type"]
        if kind in ("paragraph", "heading"):
            text = _text(block.get("text", ""), where, 200 if kind == "heading" else MAX_TEXT)
            if not text:
                continue
            item: dict[str, Any] = {"type": kind, "text": text}
            if kind == "paragraph":
                item["cites"] = _cites(block.get("cites"), where)
            blocks.append(item)
        elif kind == "bullets":
            items = block.get("items")
            if not isinstance(items, list) or len(items) > MAX_ITEMS:
                raise InvalidContent(f"{where}: items must be a list of at most {MAX_ITEMS}.")
            texts = [_text(x, where, 600) for x in items]
            texts = [t for t in texts if t]
            if texts:
                blocks.append(
                    {"type": "bullets", "items": texts, "cites": _cites(block.get("cites"), where)}
                )
        else:
            columns, rows = block.get("columns"), block.get("rows")
            if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_COLUMNS:
                raise InvalidContent(f"{where}: a table needs 1 to {MAX_COLUMNS} columns.")
            if not isinstance(rows, list) or len(rows) > MAX_ROWS:
                raise InvalidContent(f"{where}: a table can have at most {MAX_ROWS} rows.")
            cols = [_text(c, where, 60) for c in columns]
            body: list[list[str]] = []
            for row in rows:
                if not isinstance(row, list) or len(row) != len(cols):
                    raise InvalidContent(f"{where}: every row needs {len(cols)} cells.")
                body.append([_text(cell, where, 200) for cell in row])
            blocks.append(
                {
                    "type": "table",
                    "columns": cols,
                    "rows": body,
                    "cites": _cites(block.get("cites"), where),
                }
            )
    return {"blocks": blocks}


def text_of(content: dict[str, Any]) -> str:
    """All the words of a section, for search, word counts and figure checks."""
    parts: list[str] = []
    for block in content.get("blocks", []):
        kind = block.get("type")
        if kind in ("paragraph", "heading"):
            parts.append(block.get("text", ""))
        elif kind == "bullets":
            parts.extend(block.get("items", []))
        elif kind == "table":
            parts.append(" ".join(block.get("columns", [])))
            parts.extend(" ".join(row) for row in block.get("rows", []))
    return "\n".join(p for p in parts if p)


def word_count(content: dict[str, Any]) -> int:
    return len(text_of(content).split())


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def figures(text: str) -> set[str]:
    """The numbers in a text, normalised (``1,200`` and ``1200`` are the same figure)."""
    found: set[str] = set()
    for match in _NUMBER.findall(text):
        digits = match.replace(",", "").rstrip(".")
        if digits:
            found.add(digits.lstrip("0") or "0")
    return found


def unsupported_figures(text: str, allowed: str) -> set[str]:
    """Figures in ``text`` that appear nowhere in ``allowed`` (the venture's own data and the
    sourced facts). Years and the numbers 0 to 10 are ordinary words, not claims."""
    ok = figures(allowed)
    bad = set()
    for n in figures(text):
        if n in ok:
            continue
        if n.isdigit() and (int(n) <= 10 or 1990 <= int(n) <= 2100):
            continue
        bad.add(n)
    return bad


def drop_sentences_with(content: dict[str, Any], numbers: set[str]) -> dict[str, Any]:
    """Remove sentences (or bullets, or table rows) that carry an unsupported figure."""

    def has_bad(piece: str) -> bool:
        return bool(figures(piece) & numbers)

    blocks: list[dict[str, Any]] = []
    for block in content.get("blocks", []):
        kind = block.get("type")
        if kind == "paragraph":
            sentences = re.split(r"(?<=[.!?])\s+", block["text"])
            kept = [s for s in sentences if not has_bad(s)]
            if kept:
                blocks.append({**block, "text": " ".join(kept)})
        elif kind == "bullets":
            kept_items = [i for i in block["items"] if not has_bad(i)]
            if kept_items:
                blocks.append({**block, "items": kept_items})
        elif kind == "table":
            rows = [r for r in block["rows"] if not has_bad(" ".join(r))]
            if rows:
                blocks.append({**block, "rows": rows})
        else:
            blocks.append(block)
    return {"blocks": blocks}
