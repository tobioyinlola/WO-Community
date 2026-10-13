"""Base for anonymous, cacheable endpoints: the public directory, job pages and the like."""

import hashlib
import json
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle
from rest_framework.views import APIView

from apps.core import policies

# Pages are the same for everyone, so a CDN may keep them for five minutes and serve a stale
# copy while it refreshes or if the origin is down.
CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=600, stale-if-error=86400"


class SearchThrottle(SimpleRateThrottle):
    """The tighter search limit applies only to requests that actually search."""

    scope = "public_search"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        if not request.query_params.get("q"):
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class PublicView(APIView):
    """Anonymous, cookie-free and cacheable. Any Authorization header is ignored."""

    policy = policies.public
    authentication_classes: list[Any] = []
    throttle_classes = [AnonRateThrottle, SearchThrottle]
    cache_control = CACHE_CONTROL

    def cached(self, request: Request, data: Any) -> Response:
        body = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str).encode()
        tag = f'"{hashlib.sha256(body).hexdigest()[:32]}"'
        sent = request.headers.get("If-None-Match", "").removeprefix("W/")
        response = Response(status=304) if sent == tag else Response(data)
        response["ETag"] = tag
        response["Cache-Control"] = self.cache_control
        return response
