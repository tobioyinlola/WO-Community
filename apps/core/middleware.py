import time
import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

logger = structlog.get_logger("request")

CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"


class RequestContextMiddleware:
    """Assigns a request id, binds it to every log line and logs one summary line."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _valid_request_id(incoming) else uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.request_id = request_id  # type: ignore[attr-defined]
        started = time.monotonic()
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        match = getattr(request, "resolver_match", None)
        logger.info(
            "request",
            method=request.method,
            route=match.route if match else request.path,
            status=response.status_code,
            duration_ms=round((time.monotonic() - started) * 1000, 1),
        )
        return response


def _valid_request_id(value: str) -> bool:
    return 8 <= len(value) <= 64 and value.replace("-", "").isalnum()


class SecurityHeadersMiddleware:
    """Headers Django's SecurityMiddleware does not set.

    The API never renders HTML, so the CSP is the strictest possible.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", CSP)
        response.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        response.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response
