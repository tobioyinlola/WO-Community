"""Optimistic concurrency with ETag and If-Match.

Records edited from several places return an ETag. An update must send it back
in ``If-Match``; if the record changed meanwhile the update is refused instead
of silently overwriting the other change.
"""

import hashlib
from typing import Any

from rest_framework import exceptions, status
from rest_framework.response import Response


class PreconditionRequiredError(exceptions.APIException):
    status_code = status.HTTP_428_PRECONDITION_REQUIRED
    default_detail = "Send the current ETag in an If-Match header."
    default_code = "precondition_required"


class PreconditionFailedError(exceptions.APIException):
    status_code = status.HTTP_412_PRECONDITION_FAILED
    default_detail = "The record changed since you loaded it. Reload and try again."
    default_code = "precondition_failed"


def etag_for(instance: Any) -> str:
    stamp = f"{instance.pk}:{instance.updated_at.isoformat()}"
    return f'"{hashlib.sha256(stamp.encode()).hexdigest()[:32]}"'


def assert_matches(if_match: str | None, instance: Any) -> None:
    """Raise unless the header carries the instance's current ETag."""
    if not if_match:
        raise PreconditionRequiredError()
    candidate = if_match.strip()
    if candidate.startswith("W/"):
        candidate = candidate[2:]
    if candidate != etag_for(instance):
        raise PreconditionFailedError()


def add_etag(response: Response, instance: Any) -> Response:
    response["ETag"] = etag_for(instance)
    response["Cache-Control"] = "private, no-cache"
    return response
