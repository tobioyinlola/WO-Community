"""Keyset pagination for the directory.

Every ordering ends in the unique ``id``, and all columns sort ascending, so
"the rows after this one" is a plain lexicographic comparison that an index
can answer. The cursor is opaque to clients, carries the sort it belongs to,
and is checked strictly: a damaged or foreign cursor is a 400, never a guess.
"""

import base64
import binascii
import json
import uuid
from typing import Any

from django.db.models import Q, QuerySet
from rest_framework import serializers

COLUMN_TYPES: dict[str, type] = {
    "featured_rank": int,
    "newest_key": int,
    "name_key": str,
    "id": uuid.UUID,
}


def encode_cursor(sort: str, values: list[Any]) -> str:
    raw = json.dumps({"s": sort, "v": [str(v) if isinstance(v, uuid.UUID) else v for v in values]})
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, sort: str, fields: tuple[str, ...]) -> list[Any]:
    invalid = serializers.ValidationError({"cursor": ["This cursor is not valid."]})
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        values = data["v"]
        if data["s"] != sort or not isinstance(values, list) or len(values) != len(fields):
            raise invalid
        decoded: list[Any] = []
        for field, value in zip(fields, values, strict=True):
            expected = COLUMN_TYPES[field]
            if expected is int and (isinstance(value, bool) or not isinstance(value, int)):
                raise invalid
            if expected is str and not isinstance(value, str):
                raise invalid
            decoded.append(uuid.UUID(value) if expected is uuid.UUID else value)
        return decoded
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise invalid from exc


def rows_after(fields: tuple[str, ...], values: list[Any]) -> Q:
    """Rows that sort strictly after the given key, for ascending columns."""
    condition = Q()
    for i, field in enumerate(fields):
        clause = Q(**{f"{field}__gt": values[i]})
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
) -> tuple[list[Any], str | None]:
    """One page of rows and the cursor for the next, or None at the end."""
    ordered = queryset.order_by(*fields)
    if cursor:
        ordered = ordered.filter(rows_after(fields, decode_cursor(cursor, sort, fields)))
    rows = list(ordered[: limit + 1])
    if len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    last = rows[-1]
    return rows, encode_cursor(sort, [getattr(last, field) for field in fields])
