import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.notifications import centre, notify, preferences
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

LIST = "/api/v1/notifications"
READ = "/api/v1/notifications/read"
PREFS = "/api/v1/me/notification-preferences"


def active(make_user, email):
    return make_user(email=email, approved_at=timezone.now(), email_verified_at=timezone.now())


@pytest.fixture
def me(make_user):
    return active(make_user, "me@example.com")


@pytest.fixture
def actor(make_user):
    return active(make_user, "actor@example.com")


@pytest.fixture
def client(me, client_for):
    return client_for(me)


def send(me, actor, kind="comment", key=""):
    return notify.notify(
        me.pk,
        kind,
        {"actor_id": str(actor.pk), "post_id": str(uuid.uuid4()), "comment_id": str(uuid.uuid4())},
        dedupe_key=key,
    )


# --- notify() ---


def test_notify_writes_an_in_app_notification(me, actor, sent_emails):
    created = send(me, actor)
    assert created is not None and created.user_id == me.pk and created.read_at is None
    assert created.channels_sent == ["in_app", "email"]
    assert len(sent_emails) == 1 and sent_emails[0].to == "me@example.com"


def test_the_email_names_the_actor_and_links_to_the_post(me, actor, sent_emails, settings):
    from apps.profiles.services import get_or_create_profile

    profile = get_or_create_profile(actor.pk)
    profile.full_name = "Ada Obi"
    profile.save()
    created = send(me, actor)
    message = sent_emails[0]
    assert message.subject == "Ada Obi commented on your post"
    assert f"{settings.FRONTEND_BASE_URL}/posts/{created.payload['post_id']}" in message.text_body
    assert "settings/notifications" in message.text_body


def test_nobody_is_notified_about_their_own_action(me, sent_emails):
    assert send(me, me) is None
    assert Notification.objects.count() == 0 and sent_emails == []


def test_inactive_members_are_not_notified(make_user, actor, sent_emails):
    pending = make_user(email="p@example.com", status="pending")
    assert send(pending, actor) is None
    assert Notification.objects.count() == 0 and sent_emails == []


def test_a_repeated_delivery_with_the_same_key_notifies_once(me, actor, sent_emails):
    assert send(me, actor, key="evt:1") is not None
    assert send(me, actor, key="evt:1") is None
    assert Notification.objects.count() == 1 and len(sent_emails) == 1


def test_preferences_switch_each_channel_off_separately(me, actor, sent_emails):
    preferences.update(me.pk, {"comments": {"email": False}})
    send(me, actor)
    assert Notification.objects.get().channels_sent == ["in_app"] and sent_emails == []
    preferences.update(me.pk, {"comments": {"email": True, "in_app": False}})
    assert send(me, actor) is None
    assert len(sent_emails) == 1 and Notification.objects.count() == 1


def test_mail_of_one_kind_to_one_member_is_capped_per_hour(me, actor, sent_emails):
    for _ in range(notify.EMAIL_BURST_LIMIT + 3):
        send(me, actor)
    assert len(sent_emails) == notify.EMAIL_BURST_LIMIT
    assert Notification.objects.count() == notify.EMAIL_BURST_LIMIT + 3  # still shown in-app


def test_unknown_types_are_a_programming_error(me):
    with pytest.raises(KeyError):
        notify.notify(me.pk, "nonsense", {})


def test_a_hidden_actor_is_shown_without_their_name(me, actor, client_for):
    from apps.profiles.services import get_or_create_profile

    profile = get_or_create_profile(actor.pk)
    profile.full_name = "Secret Person"
    profile.visibility = {"basics": "private"}
    profile.save()
    send(me, actor)
    title = client_for(me).get(LIST).json()["results"][0]["title"]
    assert "Secret Person" not in title and title.startswith("Community member")


# --- reading the list ---


def test_the_list_is_newest_first_with_wording_and_links(client, me, actor):
    first, second = send(me, actor), send(me, actor, "reply")
    body = client.get(LIST).json()
    assert [n["id"] for n in body["results"]] == [str(second.pk), str(first.pk)]
    item = body["results"][0]
    assert item["type"] == "reply" and item["title"].endswith("replied to your comment")
    assert item["link"] == f"/posts/{second.payload['post_id']}"
    assert item["read"] is False and item["meta"]["post_id"] == second.payload["post_id"]
    assert body["unread_count"] == 2 and body["next_cursor"] is None


def test_the_list_paginates_and_can_show_unread_only(client, me, actor):
    made = [send(me, actor) for _ in range(5)]
    seen, cursor = [], ""
    while True:
        page = client.get(LIST, {"limit": 2, "cursor": cursor}).json()
        seen += [n["id"] for n in page["results"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [str(n.pk) for n in reversed(made)]
    client.post(READ, {"ids": [str(made[4].pk)]}, format="json")
    unread = client.get(LIST, {"unread": "true"}).json()
    assert len(unread["results"]) == 4 and unread["unread_count"] == 4


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"cursor": "junk"}, {"unread": "maybe"}, {"x": 1}]
)
def test_bad_list_queries_are_refused(client, params):
    assert client.get(LIST, params).status_code == 400


def test_you_only_ever_see_your_own(client, me, actor, make_user, client_for):
    send(me, actor)
    other = active(make_user, "other@example.com")
    assert client_for(other).get(LIST).json() == {
        "results": [],
        "next_cursor": None,
        "unread_count": 0,
    }


def test_the_list_needs_an_active_member(api_client, make_user, client_for):
    assert api_client.get(LIST).status_code == 401
    assert (
        client_for(make_user(email="p@example.com", status="pending")).get(LIST).status_code == 403
    )


# --- polling with ETags ---


def test_an_unchanged_list_answers_304_and_a_change_does_not(client, me, actor):
    send(me, actor)
    first = client.get(LIST)
    tag = first["ETag"]
    assert client.get(LIST, HTTP_IF_NONE_MATCH=tag).status_code == 304
    assert client.get(LIST, HTTP_IF_NONE_MATCH=f"W/{tag}").status_code == 304
    send(me, actor)
    assert client.get(LIST, HTTP_IF_NONE_MATCH=tag).status_code == 200


def test_reading_changes_the_etag(client, me, actor):
    made = send(me, actor)
    tag = client.get(LIST)["ETag"]
    client.post(READ, {"ids": [str(made.pk)]}, format="json")
    assert client.get(LIST, HTTP_IF_NONE_MATCH=tag).status_code == 200


def test_the_etag_differs_between_members_and_between_queries(
    client, me, actor, make_user, client_for
):
    send(me, actor)
    other = client_for(active(make_user, "o@example.com"))
    assert client.get(LIST)["ETag"] != other.get(LIST)["ETag"]
    assert client.get(LIST)["ETag"] != client.get(LIST, {"unread": "true"})["ETag"]


def test_a_stale_tag_from_another_member_is_not_honoured(client, me, actor, make_user, client_for):
    send(me, actor)
    other = client_for(active(make_user, "o@example.com"))
    assert client.get(LIST, HTTP_IF_NONE_MATCH=other.get(LIST)["ETag"]).status_code == 200


# --- marking as read ---


def test_marking_some_as_read(client, me, actor):
    a, b = send(me, actor), send(me, actor)
    response = client.post(READ, {"ids": [str(a.pk)]}, format="json")
    assert response.json() == {"updated": 1, "unread_count": 1}
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.read_at is not None and b.read_at is None


def test_marking_everything_as_read_and_doing_it_twice(client, me, actor):
    send(me, actor)
    send(me, actor)
    assert client.post(READ, {"all": True}, format="json").json() == {
        "updated": 2,
        "unread_count": 0,
    }
    assert client.post(READ, {"all": True}, format="json").json()["updated"] == 0


def test_you_cannot_mark_someone_elses_notifications(client, me, actor, make_user):
    other = active(make_user, "o@example.com")
    theirs = send(other, actor)
    assert client.post(READ, {"ids": [str(theirs.pk)]}, format="json").json()["updated"] == 0
    theirs.refresh_from_db()
    assert theirs.read_at is None


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"all": False},
        {"ids": []},
        {"ids": ["x"]},
        {"ids": [str(uuid.uuid4())] * 101},
        {"ids": [str(uuid.uuid4())], "all": True},
        {"z": 1},
    ],
)
def test_bad_read_requests_are_refused(client, body):
    assert client.post(READ, body, format="json").status_code == 400


def test_marking_read_needs_an_active_member(api_client):
    assert api_client.post(READ, {"all": True}, format="json").status_code == 401


# --- housekeeping ---


def test_old_notifications_are_purged(me, actor):
    old_read, old_unread, recent = send(me, actor), send(me, actor), send(me, actor)
    now = timezone.now()
    Notification.objects.filter(pk=old_read.pk).update(
        created_at=now - timedelta(days=100), read_at=now - timedelta(days=99)
    )
    Notification.objects.filter(pk=old_unread.pk).update(created_at=now - timedelta(days=100))
    assert centre.purge_old() == 1  # read and older than 90 days
    Notification.objects.filter(pk=old_unread.pk).update(created_at=now - timedelta(days=181))
    assert centre.purge_old() == 1  # anything older than 180 days
    assert list(Notification.objects.values_list("pk", flat=True)) == [recent.pk]


def test_notification_types_are_the_ones_the_preferences_know():
    assert {spec.preference for spec in notify.TYPES.values()} <= set(preferences.DEFAULTS)
