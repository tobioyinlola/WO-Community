"""Who a user id is, for admin tables that show people next to their records."""

from typing import Any
from uuid import UUID

from apps.accounts.models import User
from apps.profiles.models import FounderProfile


def people(user_ids: Any) -> dict[UUID, dict[str, Any]]:
    """``{id: {id, name, email}}``. The name is the profile's own, else the email."""
    ids = {i for i in user_ids if i}
    emails = dict(User.objects.filter(pk__in=ids).values_list("pk", "email"))
    names = dict(FounderProfile.objects.filter(user_id__in=ids).values_list("user_id", "full_name"))
    return {
        i: {"id": i, "name": names.get(i) or emails.get(i, ""), "email": emails.get(i, "")}
        for i in ids
    }
