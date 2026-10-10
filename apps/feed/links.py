"""Preview cards for the links in a post.

A post's links are found in its cleaned HTML, at most two are kept, and each address gets one
shared ``LinkPreview`` that a worker fills in. The fetching itself is the integration's job and
is built to be safe against server-side request forgery; this module only decides what to ask for
and stores the answer as plain text plus a re-encoded image.
"""

import hashlib
import html
import re
from datetime import timedelta
from urllib.parse import urldefrag

import structlog
from django.db import transaction
from django.utils import timezone

from apps.core import events as domain_events
from apps.feed import events
from apps.feed.models import LinkPreview, Post, PostLink
from apps.integrations.linkpreview import FetchFailed, FetchRejected, get_fetcher
from apps.integrations.linkpreview.safe_http import parse_url
from apps.uploads import images
from apps.uploads import services as uploads

logger = structlog.get_logger(__name__)

HREF = re.compile(r'href="([^"]+)"')
MAX_PREVIEWS = 2
RETRY_FAILED_AFTER = timedelta(hours=1)
REFRESH_READY_AFTER = timedelta(days=7)
KEEP_UNUSED_FOR = timedelta(days=7)


def extract_urls(cleaned_html: str) -> list[str]:
    """The first few distinct web addresses in the post that are even worth asking about."""
    found: list[str] = []
    for raw in HREF.findall(cleaned_html):
        url, _ = urldefrag(html.unescape(raw))
        try:
            parse_url(url)  # offline checks only: scheme, host shape, port
        except FetchRejected:
            continue
        if url not in found:
            found.append(url)
        if len(found) == MAX_PREVIEWS:
            break
    return found


def _stale(preview: LinkPreview) -> bool:
    if preview.fetched_at is None:
        # Never fetched: a request is already on its way unless it was lost long ago.
        return timezone.now() - preview.created_at > RETRY_FAILED_AFTER
    age = timezone.now() - preview.fetched_at
    if preview.status == LinkPreview.Status.FAILED:
        return age > RETRY_FAILED_AFTER
    return age > REFRESH_READY_AFTER


def _preview_for(url: str) -> LinkPreview:
    preview, created = LinkPreview.objects.get_or_create(
        url_hash=hashlib.sha256(url.encode()).hexdigest(), defaults={"url": url}
    )
    if created or _stale(preview):
        domain_events.publish(events.LinkPreviewRequested(preview_id=str(preview.pk)))
        if preview.status == LinkPreview.Status.FAILED:
            preview.status = LinkPreview.Status.PENDING
            preview.save(update_fields=["status", "updated_at"])
    return preview


def sync(post: Post, cleaned_html: str) -> None:
    """Make the post's preview links match the addresses in its body (inside its transaction)."""
    post.links.all().delete()
    for position, url in enumerate(extract_urls(cleaned_html)):
        PostLink.objects.create(post=post, preview=_preview_for(url), position=position)


def _fail(preview: LinkPreview, code: str) -> None:
    """Record a failed fetch. A card that was already showing keeps its old content."""
    preview.attempts += 1
    preview.fail_code = code
    preview.fetched_at = timezone.now()
    if preview.status != LinkPreview.Status.READY:
        preview.status = LinkPreview.Status.FAILED
    preview.save()


def fetch(preview_id: str) -> None:
    """Fill in a preview. Runs in a worker; safe to run twice."""
    preview = LinkPreview.objects.filter(pk=preview_id).first()
    if preview is None:
        return
    try:
        result = get_fetcher().fetch(preview.url)
    except (FetchRejected, FetchFailed) as exc:
        logger.info("link_preview_failed", code=exc.code)
        _fail(preview, exc.code)
        return
    image_key = ""
    if result.image:
        try:
            image_key = uploads.store_external_image(result.image, "link_preview")
        except images.ImageRejected as exc:
            logger.info("link_preview_image_rejected", code=exc.code)
    with transaction.atomic():
        previous = preview.image_key
        preview.status = LinkPreview.Status.READY
        preview.title, preview.description = result.title, result.description
        preview.site_name = result.site_name
        preview.image_key = image_key
        preview.fail_code = ""
        preview.attempts += 1
        preview.fetched_at = timezone.now()
        preview.save()
        if previous and previous != image_key:
            uploads.release(previous)


def purge_unused() -> int:
    """Delete previews no post links to any more, and their pictures."""
    cutoff = timezone.now() - KEEP_UNUSED_FOR
    count = 0
    for preview in LinkPreview.objects.filter(posts__isnull=True, created_at__lt=cutoff):
        uploads.release(preview.image_key)
        preview.delete()
        count += 1
    return count
