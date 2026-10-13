from datetime import timedelta

import pytest
from django.utils import timezone

from apps.audit import services

pytestmark = pytest.mark.django_db

URL = "/api/v1/admin/audit"


@pytest.fixture
def boss_client(make_user, client_for):
    boss = make_user(roles=("super_admin",), email="boss@example.com")
    return client_for(boss, mfa_age=5), boss


def test_lists_newest_first_with_actor_and_target(boss_client):
    client, boss = boss_client
    services.record(actor=boss, action="member.approve", target_type="user", target_label="Ada")
    services.record(actor=boss, action="jobs.reject", target_type="job", target_label="Cook")
    rows = client.get(URL).json()["results"]
    assert [r["action"] for r in rows][:2] == ["jobs.reject", "member.approve"]
    assert rows[0]["actor"]["email"] == "boss@example.com"
    assert rows[0]["target"]["title"] == "Cook"
    assert rows[0]["outcome"] == "success"


def test_system_entries_have_no_actor(boss_client):
    client, _ = boss_client
    services.record(actor=None, action="retention.purge")
    assert client.get(URL).json()["results"][0]["actor"]["name"] == "System"


def test_secrets_are_redacted_before_they_are_stored(boss_client):
    client, boss = boss_client
    entry = services.record(
        actor=boss,
        action="settings.updated",
        before={"password": "old", "name": "A"},
        after={"password": "new", "name": "B", "nested": {"api_key": "k", "ok": 1}},
    )
    assert entry.before == {"password": "[redacted]", "name": "A"}
    assert entry.after["nested"] == {"api_key": "[redacted]", "ok": 1}
    detail = client.get(f"{URL}/{entry.id}").json()
    assert {c["field"] for c in detail["changes"]} == {"name", "nested"}
    assert "new" not in str(detail)


def test_changes_list_only_fields_that_differ(boss_client):
    client, boss = boss_client
    entry = services.record(
        actor=boss, action="member.update", before={"a": 1, "b": 2}, after={"a": 1, "b": 3}
    )
    changes = client.get(f"{URL}/{entry.id}").json()["changes"]
    assert changes == [{"field": "b", "before": 2, "after": 3}]


def test_filters_by_group_action_outcome_text_and_actor(boss_client, make_user):
    client, boss = boss_client
    other = make_user(email="other@example.com")
    services.record(actor=boss, action="member.approve", target_label="Ada Okafor")
    services.record(actor=other, action="auth.login_failed", outcome="failure")
    services.record(actor=boss, action="jobs.approve", target_label="Chef")

    def actions(**q):
        return {r["action"] for r in client.get(URL, q).json()["results"]}

    assert actions(group="members") == {"member.approve"}
    assert actions(group="security") == {"auth.login_failed"}
    assert actions(action="jobs.approve") == {"jobs.approve"}
    assert actions(outcome="failure") == {"auth.login_failed"}
    assert actions(q="okafor") == {"member.approve"}
    assert "auth.login_failed" in actions(actor="other@")
    assert actions(actor="other@") == {"auth.login_failed"}


def test_date_range_includes_the_end_day(boss_client):
    client, boss = boss_client
    services.record(actor=boss, action="member.approve")
    today = timezone.now().date()
    assert len(client.get(URL, {"date_from": today, "date_to": today}).json()["results"]) == 1
    yesterday = today - timedelta(days=1)
    assert client.get(URL, {"date_from": yesterday, "date_to": yesterday}).json()["results"] == []


def test_pages_with_a_cursor_without_repeats(boss_client):
    client, boss = boss_client
    for n in range(5):
        services.record(actor=boss, action=f"member.step{n}")
    first = client.get(URL, {"limit": 2}).json()
    assert len(first["results"]) == 2 and first["next"]
    second = client.get(first["next"]).json()
    seen = [r["id"] for r in first["results"] + second["results"]]
    assert len(seen) == len(set(seen))


def test_export_is_csv_and_is_itself_recorded(boss_client):
    client, boss = boss_client
    services.record(actor=boss, action="member.approve", target_label="Ada")
    response = client.get(f"{URL}/export", {"group": "members"})
    body = b"".join(response.streaming_content).decode()
    assert response["Content-Type"].startswith("text/csv")
    assert "member.approve" in body and "boss@example.com" in body
    assert client.get(URL, {"action": "audit.exported"}).json()["results"]


def test_the_log_cannot_be_edited_over_the_api(boss_client):
    client, boss = boss_client
    entry = services.record(actor=boss, action="member.approve")
    for method in (client.put, client.patch, client.delete, client.post):
        assert method(f"{URL}/{entry.id}", {}, format="json").status_code == 405


def test_needs_the_permission_and_a_session(make_user, client_for, api_client):
    assert api_client.get(URL).status_code == 401
    mod = make_user(roles=("community_admin",))
    assert client_for(mod, mfa_age=5).get(URL).status_code == 403
    member = make_user()
    assert client_for(member).get(URL).status_code == 403
    assert client_for(mod, mfa_age=5).get(f"{URL}/export").status_code == 403
