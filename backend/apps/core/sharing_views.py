"""Links shared outside the platform.

``/s/<kind>/<ref>`` is what a member shares. Chat apps and social sites read its title, words
and image to draw a preview; people are sent straight on to the teaser page in the web app,
which shows the brief and asks them to become a member (or sign in) for the rest.
"""

import json
import secrets
from html import escape
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core import policies, shareables
from apps.core.public import PublicView

SITE = "WO Community"
PITCH = "Join WO Community, where African founders and operators build together."


class CardSerializer(serializers.Serializer):
    kind = serializers.CharField()
    ref = serializers.CharField()
    title = serializers.CharField()
    excerpt = serializers.CharField(allow_blank=True)
    url = serializers.CharField()
    badge = serializers.CharField()
    action = serializers.CharField()
    image = serializers.CharField(allow_null=True)
    facts = serializers.ListField(child=serializers.CharField())
    by = serializers.CharField(allow_blank=True)


class PublicShareCardView(PublicView):
    @extend_schema(
        operation_id="public_share_card",
        summary="The brief of something shared outside the platform",
        description="What anyone may see of a published course, an event or a community post "
        "before signing in: a title, a few words and some facts. `kind` is course, event or "
        "post. Not found when it does not exist or may not be shared.",
        responses={200: CardSerializer, 404: OpenApiResponse(description="Not found")},
        tags=["public"],
    )
    def get(self, request: Request, kind: str, ref: str) -> Response:
        card = shareables.card(kind, ref)
        if card is None:
            raise exceptions.NotFound()
        return self.cached(request, CardSerializer(card.as_dict()).data)


def _site(path: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}"


class SharePageView(APIView):
    """The page behind a shared link. Anyone may open it; it reads nothing about the visitor."""

    policy = policies.public
    authentication_classes: list[Any] = []
    throttle_classes = [AnonRateThrottle]

    @extend_schema(exclude=True)  # a web page for link previews, not part of the API
    def get(self, request: Request, kind: str, ref: str) -> HttpResponse:
        return _share_page(kind, ref)


def _share_page(kind: str, ref: str) -> HttpResponse:
    card = shareables.card(kind, ref)
    target = _site(f"/p/{kind}/{ref}" if card else "/")
    title = f"{card.title} | {SITE}" if card else SITE
    description = card.excerpt if card and card.excerpt else PITCH
    image = (card.image if card else None) or _site("/brand/og-default.png")
    meta: dict[str, Any] = {
        "og:site_name": SITE,
        "og:type": "website",
        "og:title": card.title if card else SITE,
        "og:description": description,
        "og:url": _site(f"/s/{kind}/{ref}"),
        "og:image": image,
        "twitter:card": "summary_large_image",
        "twitter:title": card.title if card else SITE,
        "twitter:description": description,
        "twitter:image": image,
    }
    tags = "\n".join(
        f'<meta {"name" if key.startswith("twitter") else "property"}="{key}" '
        f'content="{escape(str(value))}">'
        for key, value in meta.items()
    )
    nonce = secrets.token_urlsafe(16)
    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<meta name="viewport" content="width=device-width, initial-scale=1">
{tags}
<link rel="canonical" href="{escape(meta["og:url"])}">
<meta http-equiv="refresh" content="0; url={escape(target)}">
</head>
<body>
<p><a href="{escape(target)}">Continue to {escape(SITE)}</a></p>
<script nonce="{nonce}">location.replace({_js(target)});</script>
</body>
</html>"""
    response = HttpResponse(body, status=200 if card else 404, content_type="text/html")
    response["Cache-Control"] = "public, max-age=300"
    # Only this page's own redirect may run; nothing else loads.
    response["Content-Security-Policy"] = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    )
    return response


def _js(value: str) -> str:
    # json.dumps gives a safe string literal; < is escaped so it cannot end the script block.
    return json.dumps(value).replace("<", "\\u003c")
