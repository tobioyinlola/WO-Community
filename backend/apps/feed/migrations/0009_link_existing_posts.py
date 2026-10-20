"""Make the web addresses already typed into posts and comments clickable, with a card each.

Until now an address pasted as plain text was stored as plain text, so it was neither a link nor
previewed. This turns each one into a link, and gives each post's first two addresses a preview
card that a worker then fills in, exactly as a new post would get.

It is written to be safe to run on a live database: every post and comment is handled on its own, a
failure in one is skipped, and running it again changes nothing.
"""

import hashlib
import html
import re
from urllib.parse import urldefrag

import structlog
from django.db import migrations
from django.db.models import Q

logger = structlog.get_logger(__name__)

HREF = re.compile(r'href="([^"]+)"')
MAX_PREVIEWS = 2


def link_up(apps, schema_editor):
    from apps.core.text import rich_comment, rich_post
    from apps.integrations.linkpreview.base import FetchRejected
    from apps.integrations.linkpreview.safe_http import parse_url

    Post = apps.get_model("feed", "Post")
    Comment = apps.get_model("feed", "Comment")
    LinkPreview = apps.get_model("feed", "LinkPreview")
    PostLink = apps.get_model("feed", "PostLink")
    OutboxEvent = apps.get_model("core", "OutboxEvent")

    mentions_address = Q(body__contains="http") | Q(body__icontains="www.")
    for comment in Comment.objects.filter(mentions_address, deleted_at__isnull=True).iterator():
        try:
            body = rich_comment(comment.body)
            if body != comment.body:
                Comment.objects.filter(pk=comment.pk).update(body=body)
        except Exception:  # noqa: BLE001 - one odd comment must not stop the rest
            logger.warning("link_backfill_comment_skipped", comment=str(comment.pk))

    posts = Post.objects.filter(deleted_at__isnull=True).iterator()
    for post in posts:
        try:
            body = rich_post(post.body)
            if body != post.body:
                Post.objects.filter(pk=post.pk).update(body=body)
            if PostLink.objects.filter(post_id=post.pk).exists():
                continue
            found = []
            for raw in HREF.findall(body):
                url, _ = urldefrag(html.unescape(raw))
                try:
                    parse_url(url)
                except FetchRejected:
                    continue
                if url not in found:
                    found.append(url)
                if len(found) == MAX_PREVIEWS:
                    break
            for position, url in enumerate(found):
                preview, created = LinkPreview.objects.get_or_create(
                    url_hash=hashlib.sha256(url.encode()).hexdigest(), defaults={"url": url}
                )
                PostLink.objects.create(post_id=post.pk, preview=preview, position=position)
                if created:
                    OutboxEvent.objects.create(
                        topic="feed.link_preview_requested", payload={"preview_id": str(preview.pk)}
                    )
        except Exception:  # noqa: BLE001 - one odd post must not stop the rest
            logger.warning("link_backfill_post_skipped", post=str(post.pk))


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("feed", "0008_post_shares"),
    ]

    operations = [migrations.RunPython(link_up, migrations.RunPython.noop)]
