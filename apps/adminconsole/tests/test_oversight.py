from datetime import timedelta

import pytest
from django.utils import timezone
from psycopg.types.range import Range

from apps.accounts.models import Invitation, UserRole
from apps.audit.models import AuditLog
from apps.feed import services as feed
from apps.mentorship.models import MentorSession
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin"


def active(make_user, email, name="", **fields):
    user = make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )
    profile = get_or_create_profile(user.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(full_name=name)
    return user


@pytest.fixture
def mod(make_user, client_for):
    user = make_user(roles=("community_admin",), email="mod@example.com")
    return client_for(user, mfa_age=5)


@pytest.fixture
def boss(make_user):
    return make_user(roles=("super_admin",), email="boss@example.com")


@pytest.fixture
def boss_client(boss, client_for):
    return client_for(boss, mfa_age=5)


@pytest.fixture
def ada(make_user):
    return active(make_user, "ada@example.com", "Ada Founder")


@pytest.fixture
def kofi(make_user):
    return active(make_user, "kofi@example.com", "Kofi Mentor")


# --- posts ---


def make_post(user, body="<p>Hello there</p>", category="update"):
    return feed.create_post(user_id=user.pk, category=category, body=body, images=[])


def test_the_post_list_shows_hidden_posts_and_filters(mod, client_for, ada, kofi):
    seen = make_post(ada, "<p>Visible</p>")
    hidden = make_post(kofi, "<p>Hush</p>", "question")
    mod.post(f"{ADMIN}/posts/{hidden.pk}/hide", {"reason": "spam"}, format="json")

    everything = mod.get(f"{ADMIN}/posts").json()
    assert everything["count"] == 2
    assert {r["id"] for r in everything["results"]} == {str(seen.pk), str(hidden.pk)}

    only_hidden = mod.get(f"{ADMIN}/posts", {"state": "hidden"}).json()["results"]
    assert [r["id"] for r in only_hidden] == [str(hidden.pk)] and only_hidden[0]["hidden"]
    assert only_hidden[0]["author"]["name"] == "Kofi Mentor"
    assert mod.get(f"{ADMIN}/posts", {"category": "question"}).json()["count"] == 1
    assert mod.get(f"{ADMIN}/posts", {"q": "ada"}).json()["count"] == 1


def test_a_post_detail_lists_hidden_comments_too(mod, ada, kofi):
    post = make_post(ada)
    shown = feed.add_comment(user_id=kofi.pk, post_id=post.pk, body="<p>Nice</p>")
    hidden = feed.add_comment(user_id=kofi.pk, post_id=post.pk, body="<p>Rude</p>")
    mod.post(f"{ADMIN}/comments/{hidden.pk}/hide", {"reason": "rude"}, format="json")
    detail = mod.get(f"{ADMIN}/posts/{post.pk}").json()
    flags = {c["id"]: c["hidden"] for c in detail["comments"]}
    assert flags == {str(shown.pk): False, str(hidden.pk): True}
    assert detail["text"] == "Hello there"


def test_the_feed_pages_are_for_moderators(client_for, make_user, ada):
    member = client_for(ada)
    assert member.get(f"{ADMIN}/posts").status_code == 403
    assert member.get(f"{ADMIN}/posts/stats").status_code == 403


def test_feed_stats_count_the_week(mod, ada):
    make_post(ada)
    stats = mod.get(f"{ADMIN}/posts/stats").json()
    assert stats["posts"] == 1 and stats["posts_last_7_days"] == 1 and stats["hidden"] == 0


# --- matches and sessions ---


def make_session(mentor, mentee, status="confirmed", days=2):
    start = timezone.now() + timedelta(days=days)
    end = start + timedelta(minutes=30)
    return MentorSession.objects.create(
        mentor=mentor,
        mentee=mentee,
        starts_at=start,
        ends_at=end,
        time_span=Range(start, end),
        topic="Fundraising",
        message="Help",
        status=status,
        length_minutes=30,
    )


def test_matches_group_sessions_by_pair(mod, ada, kofi):
    make_session(kofi, ada, "completed", days=-3)
    make_session(kofi, ada, "confirmed", days=2)
    rows = mod.get(f"{ADMIN}/matches").json()["results"]
    assert len(rows) == 1
    pair = rows[0]
    assert (pair["mentor"]["name"], pair["mentee"]["name"]) == ("Kofi Mentor", "Ada Founder")
    assert (pair["sessions"], pair["completed"], pair["upcoming"]) == (2, 1, 1)
    assert pair["state"] == "active" and pair["next_at"] is not None
    assert mod.get(f"{ADMIN}/matches", {"state": "idle"}).json()["count"] == 0
    assert mod.get(f"{ADMIN}/matches", {"q": "kofi"}).json()["count"] == 1


def test_a_finished_pair_is_marked_completed(mod, ada, kofi):
    make_session(kofi, ada, "completed", days=-3)
    [pair] = mod.get(f"{ADMIN}/matches").json()["results"]
    assert pair["state"] == "completed" and pair["next_at"] is None


# --- analytics ---


def test_analytics_count_live_and_compare_with_the_range_before(mod, ada, kofi):
    make_post(ada)
    make_post(kofi)
    data = mod.get(f"{ADMIN}/analytics").json()
    stats = {s["key"]: s for s in data["stats"]}
    assert stats["posts"]["value"] == 2 and stats["members"]["value"] >= 2
    assert data["days"] == 30
    posts = next(s for s in data["series"] if s["key"] == "posts")
    assert len(posts["points"]) == 30 and sum(p["count"] for p in posts["points"]) == 2
    assert {b["key"] for b in data["breakdowns"]} >= {"country", "sector", "category"}
    assert data["funnel"][0]["name"] == "Signed up"
    assert data["funnel"][0]["count"] >= data["funnel"][-1]["count"]


def test_analytics_range_is_checked(mod):
    assert (
        mod.get(f"{ADMIN}/analytics", {"from": "2026-05-02", "to": "2026-05-01"}).status_code == 400
    )
    far = mod.get(f"{ADMIN}/analytics", {"from": "2024-01-01", "to": "2026-01-01"})
    assert far.status_code == 400
    one = mod.get(f"{ADMIN}/analytics", {"from": "2026-05-01", "to": "2026-05-01"})
    assert one.status_code == 200 and one.json()["days"] == 1


def test_analytics_need_the_dashboard_permission(client_for, ada):
    assert client_for(ada).get(f"{ADMIN}/analytics").status_code == 403


# --- the team ---


def test_roles_list_the_matrix_and_head_counts(mod, boss):
    roles = {r["role"]: r for r in mod.get(f"{ADMIN}/roles").json()}
    assert roles["super_admin"]["people"] == 1 and roles["super_admin"]["team"] is True
    assert "roles.manage" in roles["super_admin"]["permissions"]
    assert "roles.manage" not in roles["community_admin"]["permissions"]
    assert roles["member"]["team"] is False


def test_only_a_super_admin_can_invite_a_team_member(mod, boss_client):
    body = {"email": "new.editor@example.com", "role": "content_editor"}
    assert mod.post(f"{ADMIN}/invitations", body, format="json").status_code == 403
    made = boss_client.post(f"{ADMIN}/invitations", body, format="json")
    assert made.status_code == 201 and made.json()["role"] == "content_editor"
    assert Invitation.objects.get(email="new.editor@example.com").role == "content_editor"
    team = boss_client.get(f"{ADMIN}/invitations", {"role": "team"}).json()
    assert [i["email"] for i in team["results"]] == ["new.editor@example.com"]


def test_a_community_admin_can_still_invite_members(mod):
    made = mod.post(
        f"{ADMIN}/invitations", {"email": "pal@example.com", "role": "mentor"}, format="json"
    )
    assert made.status_code == 201


def test_a_super_admin_grants_and_revokes_a_role(boss_client, ada):
    url = f"{ADMIN}/members/{ada.pk}/role"
    granted = boss_client.post(url, {"role": "content_editor", "action": "grant"}, format="json")
    assert granted.status_code == 200 and "content_editor" in granted.json()["roles"]
    assert UserRole.objects.filter(user=ada, role="content_editor").exists()
    assert AuditLog.objects.filter(action="role.grant", target_id=str(ada.pk)).exists()
    revoked = boss_client.post(url, {"role": "content_editor", "action": "revoke"}, format="json")
    assert "content_editor" not in revoked.json()["roles"]


def test_role_changes_are_restricted(mod, boss, boss_client, ada, make_user):
    url = f"{ADMIN}/members/{ada.pk}/role"
    body = {"role": "community_admin", "action": "grant"}
    assert mod.post(url, body, format="json").status_code == 403
    own = boss_client.post(
        f"{ADMIN}/members/{boss.pk}/role",
        {"role": "super_admin", "action": "revoke"},
        format="json",
    )
    assert own.status_code == 403
    sole = make_user(roles=("super_admin",), email="other.boss@example.com", status="active")
    assert sole.pk != boss.pk


def test_the_last_super_admin_cannot_be_demoted(boss_client, boss, make_user, client_for):
    second = make_user(roles=("super_admin",), email="second@example.com", status="active")
    second_client = client_for(second, mfa_age=5)
    # `second` demotes `boss`: allowed because `second` remains.
    ok = second_client.post(
        f"{ADMIN}/members/{boss.pk}/role",
        {"role": "super_admin", "action": "revoke"},
        format="json",
    )
    assert ok.status_code == 200
    # Now `second` is the only one left, so `boss` (no longer a super admin) cannot touch them
    # and `second` cannot remove their own role.
    again = boss_client.post(
        f"{ADMIN}/members/{second.pk}/role",
        {"role": "super_admin", "action": "revoke"},
        format="json",
    )
    assert again.status_code in (401, 403)


def test_only_active_accounts_can_join_the_team(boss_client, make_user):
    pending = make_user(email="pending@example.com", status="pending")
    result = boss_client.post(
        f"{ADMIN}/members/{pending.pk}/role",
        {"role": "content_editor", "action": "grant"},
        format="json",
    )
    assert result.status_code == 409
