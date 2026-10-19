import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.groups.models import ChatGroup, GroupMessage

pytestmark = pytest.mark.django_db

GROUPS = "/api/v1/groups"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def ada(make_user, client_for):
    return client_for(active(make_user, "ada@example.com"))


@pytest.fixture
def tunde(make_user, client_for):
    return client_for(active(make_user, "tunde@example.com"))


@pytest.fixture
def admin(make_user, client_for):
    return client_for(make_user(roles=("community_admin",), email="admin@example.com"), mfa_age=5)


def group(name="WO Sport Group"):
    return ChatGroup.objects.get(name=name)


def messages_url(g):
    return f"{GROUPS}/{g.pk}/messages"


def join(client, g):
    assert client.post(f"{GROUPS}/{g.pk}/membership").status_code == 200


def test_the_three_starter_groups_are_there(ada):
    names = [g["name"] for g in ada.get(GROUPS).json()]
    assert names[:3] == ["WO Men's Group", "WO Women's Group", "WO Sport Group"]
    assert all(not g["joined"] for g in ada.get(GROUPS).json())


def test_join_talk_reply_react_and_leave(ada, tunde):
    g = group()
    join(ada, g)
    join(tunde, g)
    join(tunde, g)  # joining twice is fine
    sent = ada.post(
        messages_url(g), {"body": "Who is watching the match tonight? ⚽🔥"}, format="json"
    )
    assert sent.status_code == 201, sent.content
    first = sent.json()
    assert first["body"] == "Who is watching the match tonight? ⚽🔥" and first["mine"]

    reply = tunde.post(
        messages_url(g), {"body": "Me! 🙌", "reply_to": first["id"]}, format="json"
    ).json()
    assert reply["reply_to"]["id"] == first["id"]
    assert reply["reply_to"]["text"].startswith("Who is watching")

    react = f"/api/v1/group-messages/{first['id']}/reactions"
    on = tunde.post(react, {"emoji": "😂"}, format="json").json()
    assert on == {"on": True, "reactions": [{"emoji": "😂", "count": 1, "mine": True}]}
    ada.post(react, {"emoji": "😂"}, format="json")
    ada.post(react, {"emoji": "👍🏾"}, format="json")
    page = ada.get(messages_url(g)).json()["results"]
    assert [m["body"] for m in page] == ["Who is watching the match tonight? ⚽🔥", "Me! 🙌"]
    assert page[0]["reactions"] == [
        {"emoji": "😂", "count": 2, "mine": True},
        {"emoji": "👍🏾", "count": 1, "mine": True},
    ]
    off = tunde.post(react, {"emoji": "😂"}, format="json").json()
    assert off["on"] is False and off["reactions"][0]["count"] == 1

    assert tunde.delete(f"{GROUPS}/{g.pk}/membership").json() == {"joined": False}
    assert tunde.get(messages_url(g)).status_code == 403


@pytest.mark.parametrize("emoji", ["like", "", "<b>", "!!!", "😂" * 20])
def test_only_emoji_count_as_reactions(ada, emoji):
    g = group()
    join(ada, g)
    sent = ada.post(messages_url(g), {"body": "Hi"}, format="json").json()
    response = ada.post(
        f"/api/v1/group-messages/{sent['id']}/reactions", {"emoji": emoji}, format="json"
    )
    assert response.status_code == 400


def test_outsiders_can_not_read_or_post(ada):
    g = group()
    assert ada.get(messages_url(g)).status_code == 403
    assert ada.post(messages_url(g), {"body": "Hi"}, format="json").status_code == 403


def test_markup_is_stripped_and_blank_messages_are_refused(ada):
    g = group()
    join(ada, g)
    sent = ada.post(messages_url(g), {"body": "<script>x</script>Hello <b>all</b>"}, format="json")
    assert sent.json()["body"] == "Hello all"
    assert ada.post(messages_url(g), {"body": "   "}, format="json").status_code == 400


def test_only_the_author_deletes_a_message(ada, tunde):
    g = group()
    join(ada, g)
    join(tunde, g)
    mine = ada.post(messages_url(g), {"body": "Oops"}, format="json").json()
    assert tunde.delete(f"/api/v1/group-messages/{mine['id']}").status_code == 403
    assert ada.delete(f"/api/v1/group-messages/{mine['id']}").status_code == 204
    shown = tunde.get(messages_url(g)).json()["results"][0]
    assert shown["deleted"] and shown["body"] == "" and not shown["removed"]


def test_unread_counts_others_messages_until_read(ada, tunde):
    g = group()
    join(ada, g)
    join(tunde, g)
    ada.post(messages_url(g), {"body": "One"}, format="json")
    ada.post(messages_url(g), {"body": "Two"}, format="json")
    sport = next(x for x in tunde.get(GROUPS).json() if x["id"] == str(g.pk))
    assert sport["unread"] == 2 and sport["last_message"]["text"] == "Two"
    tunde.get(messages_url(g))
    sport = next(x for x in tunde.get(GROUPS).json() if x["id"] == str(g.pk))
    assert sport["unread"] == 0


def test_older_messages_page_backwards(ada):
    g = group()
    join(ada, g)
    for i in range(5):
        ada.post(messages_url(g), {"body": f"m{i}"}, format="json")
    page = ada.get(messages_url(g), {"limit": 2}).json()
    assert [m["body"] for m in page["results"]] == ["m3", "m4"]
    earlier = ada.get(messages_url(g), {"limit": 2, "cursor": page["older"]}).json()
    assert [m["body"] for m in earlier["results"]] == ["m1", "m2"]


def test_admins_create_rename_and_archive_groups(admin, ada):
    made = admin.post(
        "/api/v1/admin/groups", {"name": "WO Founders in Tech", "emoji": "💻"}, format="json"
    )
    assert made.status_code == 201, made.content
    created = made.json()
    assert created["name"] == "WO Founders in Tech" and not created["archived"]
    assert "WO Founders in Tech" in [g["name"] for g in ada.get(GROUPS).json()]

    clash = admin.post("/api/v1/admin/groups", {"name": "wo sport group"}, format="json")
    assert clash.status_code == 400

    url = f"/api/v1/admin/groups/{created['id']}"
    renamed = admin.patch(url, {"name": "WO Tech Founders"}, format="json").json()
    assert renamed["name"] == "WO Tech Founders"
    assert admin.patch(url, {"archived": True}, format="json").json()["archived"] is True
    assert "WO Tech Founders" not in [g["name"] for g in ada.get(GROUPS).json()]
    assert AuditLog.objects.filter(action="groups.created").exists()


def test_admins_read_and_remove_messages(admin, ada):
    g = group()
    join(ada, g)
    bad = ada.post(messages_url(g), {"body": "Buy followers cheap"}, format="json").json()
    seen = admin.get(f"/api/v1/admin/groups/{g.pk}/messages").json()["results"]
    assert seen[0]["body"] == "Buy followers cheap"
    assert admin.delete(f"/api/v1/admin/group-messages/{bad['id']}").status_code == 204
    shown = ada.get(messages_url(g)).json()["results"][0]
    assert shown["removed"] and shown["body"] == ""
    assert GroupMessage.objects.get(pk=bad["id"]).body == "Buy followers cheap"  # kept, hidden
    assert AuditLog.objects.filter(action="groups.message_removed").exists()


def test_members_can_not_manage_groups(ada):
    assert ada.get("/api/v1/admin/groups").status_code == 403
    assert ada.post("/api/v1/admin/groups", {"name": "Mine"}, format="json").status_code == 403
