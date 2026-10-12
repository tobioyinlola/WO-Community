import pytest
from django.utils import timezone

from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

FOLLOWS = "/api/v1/follows"
SUGGESTIONS = "/api/v1/me/follow-suggestions"


def member(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


def named(user, name, **fields):
    from apps.profiles.models import FounderProfile

    return FounderProfile.objects.update_or_create(
        user=user,
        defaults={"full_name": name, "slug": name.lower().replace(" ", "-"), **fields},
    )[0]


@pytest.fixture
def ada(make_user):
    user = member(make_user, "ada@example.com")
    named(user, "Ada Obi", country="NG")
    return user


@pytest.fixture
def kofi(make_user):
    user = member(make_user, "kofi@example.com")
    named(user, "Kofi Mensah", country="GH")
    return user


# --- notices ---


def test_the_person_followed_is_told_once(ada, kofi, client_for, run_outbox):
    client = client_for(kofi)
    assert (
        client.post(FOLLOWS, {"type": "member", "id": str(ada.pk)}, format="json").status_code
        == 201
    )
    run_outbox()
    note = Notification.objects.get(user=ada, type="new_follower")
    assert note.payload["actor_id"] == str(kofi.pk)
    # Unfollowing and following again is quiet, and so is a repeated follow.
    client.delete(f"{FOLLOWS}/member/{ada.pk}")
    client.post(FOLLOWS, {"type": "member", "id": str(ada.pk)}, format="json")
    client.post(FOLLOWS, {"type": "member", "id": str(ada.pk)}, format="json")
    run_outbox()
    assert Notification.objects.filter(user=ada, type="new_follower").count() == 1


def test_the_notice_reads_well_and_sends_no_email_by_default(
    ada, kofi, client_for, run_outbox, sent_emails
):
    client_for(kofi).post(FOLLOWS, {"type": "member", "id": str(ada.pk)}, format="json")
    run_outbox()
    body = client_for(ada).get("/api/v1/notifications").json()
    titles = [n["title"] for n in body["results"]]
    assert titles == ["Kofi Mensah started following you"]
    assert [m for m in sent_emails if m.to == "ada@example.com"] == []


def test_following_can_be_switched_off(ada, kofi, client_for, run_outbox):
    prefs = client_for(ada).put(
        "/api/v1/me/notification-preferences",
        {"preferences": {"follows": {"in_app": False}}},
        format="json",
    )
    assert prefs.status_code == 200, prefs.content
    client_for(kofi).post(FOLLOWS, {"type": "member", "id": str(ada.pk)}, format="json")
    run_outbox()
    assert not Notification.objects.filter(user=ada, type="new_follower").exists()


# --- suggestions ---


def test_suggestions_rank_by_what_is_shared_and_leave_out_followed_people(
    make_user, ada, kofi, client_for
):
    near = member(make_user, "near@example.com")
    named(near, "Near Ada", country="NG")
    far = member(make_user, "far@example.com")
    named(far, "Far Away", country="KE")
    followed = member(make_user, "followed@example.com")
    named(followed, "Already Followed", country="NG")
    client = client_for(ada)
    client.post(FOLLOWS, {"type": "member", "id": str(followed.pk)}, format="json")

    body = client.get(SUGGESTIONS).json()
    names = [s["name"] for s in body]
    assert "Already Followed" not in names and "Ada Obi" not in names
    assert names[0] == "Near Ada"  # same country
    first = body[0]
    assert "In your country" in first["reasons"] and first["score"] >= 2
    assert set(first) == {"id", "slug", "name", "headline", "image", "score", "reasons"}


def test_social_proof_lifts_a_candidate(make_user, ada, client_for):
    friend = member(make_user, "friend@example.com")
    named(friend, "Friend", country="ZA")
    popular = member(make_user, "popular@example.com")
    named(popular, "Popular One", country="ZA")
    other = member(make_user, "other@example.com")
    named(other, "Other One", country="ZA")
    client_for(ada).post(FOLLOWS, {"type": "member", "id": str(friend.pk)}, format="json")
    client_for(friend).post(FOLLOWS, {"type": "member", "id": str(popular.pk)}, format="json")
    body = client_for(ada).get(SUGGESTIONS).json()
    assert body[0]["name"] == "Popular One"
    assert "Followed by someone you follow" in body[0]["reasons"]


def test_hidden_and_inactive_members_are_never_suggested(make_user, ada, client_for):
    gone = member(make_user, "gone@example.com", status="suspended")
    named(gone, "Gone Person", country="NG")
    noprofile = member(make_user, "bare@example.com")
    assert noprofile
    body = client_for(ada).get(SUGGESTIONS).json()
    assert [s["name"] for s in body] == []


def test_suggestions_are_private_limited_and_validated(ada, client_for, api_client):
    client = client_for(ada)
    assert client.get(SUGGESTIONS, {"limit": 31}).status_code == 400
    assert client.get(SUGGESTIONS)["Cache-Control"] == "private, no-store"
    assert api_client.get(SUGGESTIONS).status_code == 401
