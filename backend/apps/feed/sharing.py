"""A community post as a share card, for a link shared outside the platform.

Only posts meant for every member can be shared, and only once they are out. The author is
named only if their name is public; otherwise the card says a community member wrote it.
"""

from uuid import UUID

from apps.accounts import services as accounts
from apps.core import shareables
from apps.feed.models import Post
from apps.profiles import selectors as profiles
from apps.uploads import services as uploads

LABELS = {
    "win": "Celebration",
    "event": "Event",
    "opportunity": "Opportunity",
    "resource": "Resource",
    "question": "Question",
    "update": "Update",
}
WHAT = {
    "win": "a win",
    "event": "an event",
    "opportunity": "an opportunity",
    "resource": "a resource",
    "question": "a question",
    "update": "an update",
}


def post_card(ref: str) -> shareables.Card | None:
    try:
        post_id = UUID(ref)
    except ValueError:
        return None
    post = (
        Post.objects.filter(
            pk=post_id,
            deleted_at__isnull=True,
            hidden_at__isnull=True,
            scheduled_for__isnull=True,
            audience_roles=[],
            author_id__in=accounts.active_user_ids(),
        )
        .prefetch_related("images")
        .first()
    )
    if post is None:
        return None
    if post.official:
        by = "WO Community team"
    else:
        author = profiles.cards_for(None, [post.author_id])[post.author_id]
        by = author["name"] if not author["hidden"] else "Community member"
    image = next(iter(post.images.all()), None)
    urls = uploads.image_urls(image.base_key) if image else None
    return shareables.Card(
        kind="post",
        ref=str(post.pk),
        title=f"{by} shared {WHAT.get(post.category, 'a post')}",
        excerpt=shareables.excerpt(post.body_text, 160),
        url=f"/app/feed/{post.pk}",
        badge=LABELS.get(post.category, "Post"),
        action="Read the post",
        image=urls["large"] if urls else None,
        by=by,
    )
