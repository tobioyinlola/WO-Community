"""Single error format for the whole API (RFC 9457 problem details)."""

from typing import Any

import structlog
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = structlog.get_logger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"
TYPE_BASE = "https://api.wocommunity.example/problems/"


class ConflictError(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


class MfaRequired(exceptions.PermissionDenied):
    default_detail = "Multi-factor authentication is required for this action."
    default_code = "mfa_required"


class StepUpRequired(exceptions.PermissionDenied):
    default_detail = "Confirm your identity again to perform this action."
    default_code = "step_up_required"


def _problem(
    http_status: int, code: str, title: str, detail: str, errors: Any = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{TYPE_BASE}{code}",
        "title": title,
        "status": http_status,
        "detail": detail,
        "code": code,
    }
    if errors:
        body["errors"] = errors
    return body


def _flatten(detail: Any) -> Any:
    if isinstance(detail, dict):
        return {key: _flatten(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_flatten(item) for item in detail]
    return str(detail)


def problem_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, exceptions.APIException):
        response = drf_exception_handler(exc, context)
        if response is None:  # pragma: no cover - drf always handles APIException
            return None
        code = _code_for(exc)
        errors = _flatten(exc.detail) if isinstance(exc, exceptions.ValidationError) else None
        detail = _detail_for(exc)
        response.data = _problem(
            response.status_code, code, _title_for(response.status_code), detail, errors
        )
        response.content_type = PROBLEM_CONTENT_TYPE
        return response

    logger.exception("unhandled_exception", view=type(context.get("view")).__name__)
    response = Response(
        _problem(500, "server_error", "Server error", "An unexpected error occurred."),
        status=500,
    )
    response.content_type = PROBLEM_CONTENT_TYPE
    return response


def _code_for(exc: exceptions.APIException) -> str:
    if isinstance(exc, exceptions.ValidationError):
        return "validation_error"
    if isinstance(exc, exceptions.Throttled):
        return "rate_limited"
    if isinstance(exc, exceptions.ParseError):
        return "malformed_request"
    return str(exc.get_codes()) if isinstance(exc.get_codes(), str) else exc.default_code


def _detail_for(exc: exceptions.APIException) -> str:
    if isinstance(exc, exceptions.ValidationError):
        return "The request contains invalid data."
    return str(exc.detail)


def _title_for(http_status: int) -> str:
    return {
        400: "Bad request",
        401: "Authentication required",
        403: "Permission denied",
        404: "Not found",
        405: "Method not allowed",
        409: "Conflict",
        412: "Precondition failed",
        415: "Unsupported media type",
        429: "Too many requests",
    }.get(http_status, "Request failed")
