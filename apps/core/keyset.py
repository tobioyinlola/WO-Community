"""Keyset pagination for feeds and comment lists.

Every ordering ends in the unique ``id`` and runs the same direction on every column, so "the rows
after this one" is a plain lexicographic comparison an index can answer. The cursor is opaque,
names the ordering it belongs to, and is checked strictly: a damaged or foreign cursor is a 400.
"""

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Any

from django.db.models import Q, QuerySet
from rest_framework import serializers

PARSERS: dict[str, Any] = {
    "created_at": datetime.fromisoformat,
    "published_at": datetime.fromisoformat,
    "starts_at": datetime.fromisoformat,
    "engagement": int,
    "id": uuid.UUID,
}


def _encode(sort: str, values: list[Any]) -> str:
    raw = json.dumps(
        {"s": sort, "v": [v.isoformat() if isinstance(v, datetime) else str(v) for v in values]}
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode(cursor: str, sort: str, fields: tuple[str, ...]) -> list[Any]:
    invalid = serializers.ValidationError({"cursor": ["This cursor is not valid."]})
    try:
        data = json.loads(base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode()))
        if data["s"] != sort or len(data["v"]) != len(fields):
            raise invalid
        return [PARSERS[f](v) for f, v in zip(fields, data["v"], strict=True)]
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise invalid from exc


def _after(fields: tuple[str, ...], values: list[Any], descending: bool) -> Q:
    lookup = "lt" if descending else "gt"
    condition = Q()
    for i, field in enumerate(fields):
        clause = Q(**{f"{field}__{lookup}": values[i]})
        for j in range(i):
            clause &= Q(**{fields[j]: values[j]})
        condition |= clause
    return condition


def paginate(
    queryset: QuerySet[Any],
    *,
    fields: tuple[str, ...],
    sort: str,
    cursor: str,
    limit: int,
    descending: bool = True,
) -> tuple[list[Any], str | None]:
    """One page of rows and the cursor for the next, or None at the end."""
    prefix = "-" if descending else ""
    ordered = queryset.order_by(*[prefix + f for f in fields])
    if cursor:
        ordered = ordered.filter(_after(fields, _decode(cursor, sort, fields), descending))
    rows = list(ordered[: limit + 1])
    if len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    return rows, _encode(sort, [getattr(rows[-1], f) for f in fields])
