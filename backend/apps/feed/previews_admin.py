"""What moderators can do about link preview cards: look them up, refetch, and block a site.

A blocked domain (and every subdomain of it) never gets a card: nothing is fetched from it, cards
that already exist for it are taken down at once, and posts that link to it keep the plain link.
"""

import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from rest_framework import exceptions

from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core.text import plain
from apps.feed import events
from apps.feed.models import BlockedDomain, LinkPreview
from apps.uploads import services as uploads

DOMAIN = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def clean_domain(value: str) -> str:
    """A bare registrable domain. Pasting a whole address is fine: its host is used."""
    text = value.strip().lower()
    if "://" in text:
        text = urlsplit(text).hostname or ""
    text = text.removeprefix("www.").rstrip(".")
    try:
        text = text.encode("idna").decode()
    except UnicodeError as exc:
        raise exceptions.ValidationError({"domain": ["That is not a valid domain."]}) from exc
    if not DOMAIN.match(text):
        raise exceptions.ValidationError({"domain": ["Enter a domain such as example.com."]})
    return text


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_blocked(url: str) -> bool:
    host = host_of(url)
    if not host:
        return False
    parts = host.split(".")
    candidates = {".".join(parts[i:]) for i in range(len(parts) - 1)}
    return BlockedDomain.objects.filter(domain__in=candidates).exists()


def _matching(domain: str) -> QuerySet[LinkPreview]:
    """Previews whose address is on ``domain`` or a subdomain of it."""
    return LinkPreview.objects.filter(
        url__iregex=rf"^https?://([^/@:]+\.)?{re.escape(domain)}([:/?#]|$)"
    )


def _take_down(preview: LinkPreview) -> None:
    previous = preview.image_key
    preview.status = LinkPreview.Status.FAILED
    preview.fail_code = "blocked_domain"
    preview.title = preview.description = preview.site_name = preview.image_key = ""
    preview.save()
    uploads.release(previous)


# --- previews ---


def previews(*, q: str = "", status: str = "") -> QuerySet[LinkPreview]:
    queryset = LinkPreview.objects.all()
    if q:
        queryset = queryset.filter(url__icontains=q)
    if status:
        queryset = queryset.filter(status=status)
    return queryset.order_by("-created_at", "id")


def preview_view(preview: LinkPreview) -> dict[str, Any]:
    return {
        "id": preview.pk,
        "url": preview.url,
        "domain": host_of(preview.url),
        "status": preview.status,
        "title": preview.title,
        "site_name": preview.site_name,
        "fail_code": preview.fail_code,
        "attempts": preview.attempts,
        "fetched_at": preview.fetched_at,
        "posts": preview.posts.count(),
        "blocked": is_blocked(preview.url),
    }


def refresh(*, actor: Any, preview_id: UUID, ip: str = "") -> LinkPreview:
    """Fetch the card again now (for example after the site fixed its page)."""
    with transaction.atomic():
        preview = LinkPreview.objects.select_for_update().filter(pk=preview_id).first()
        if preview is None:
            raise exceptions.NotFound()
        if is_blocked(preview.url):
            raise exceptions.ValidationError({"domain": ["This site is blocked."]})
        preview.status = LinkPreview.Status.PENDING
        preview.fail_code = ""
        preview.save(update_fields=["status", "fail_code", "updated_at"])
        domain_events.publish(events.LinkPreviewRequested(preview_id=str(preview.pk)))
        audit.record(
            actor=actor,
            action="feed.link_preview_refreshed",
            target_type="link_preview",
            target_id=preview.pk,
            ip=ip,
        )
    return preview


# --- blocked domains ---


def blocked() -> QuerySet[BlockedDomain]:
    return BlockedDomain.objects.order_by("domain")


def block(*, actor: Any, domain: str, reason: str, ip: str = "") -> BlockedDomain:
    name = clean_domain(domain)
    note = plain(reason)
    try:
        with transaction.atomic():
            entry = BlockedDomain.objects.create(domain=name, reason=note, created_by=actor)
            for preview in _matching(name):
                _take_down(preview)
            audit.record(
                actor=actor,
                action="feed.domain_blocked",
                target_type="blocked_domain",
                target_id=entry.pk,
                after={"domain": name},
                reason=note,
                ip=ip,
            )
    except IntegrityError as exc:
        raise exceptions.ValidationError({"domain": ["This domain is already blocked."]}) from exc
    return entry


def unblock(*, actor: Any, entry_id: UUID, ip: str = "") -> None:
    with transaction.atomic():
        entry = BlockedDomain.objects.select_for_update().filter(pk=entry_id).first()
        if entry is None:
            raise exceptions.NotFound()
        domain = entry.domain
        entry.delete()
        audit.record(
            actor=actor,
            action="feed.domain_unblocked",
            target_type="blocked_domain",
            target_id=entry_id,
            after={"domain": domain},
            ip=ip,
        )
