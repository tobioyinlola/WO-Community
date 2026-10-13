import pytest

from apps.audit.models import AuditLog
from apps.integrations.email.fake import FakeEmailAdapter
from apps.notifications import mailtemplates as mt

pytestmark = pytest.mark.django_db

BASE = "/api/v1/admin/email-templates"


@pytest.fixture(autouse=True)
def clear_sent():
    FakeEmailAdapter.reset()


@pytest.fixture
def admin_client(make_user, client_for):
    return client_for(make_user(roles=("community_admin",), email="mod@example.com"), mfa_age=5)


def body(**fields):
    base = {
        "subject": "You are in",
        "preheader": "Welcome",
        "body": "You are in!\n\n[button: Sign in | {{login_url}}]",
    }
    base.update(fields)
    return base


def test_lists_every_template(admin_client):
    rows = admin_client.get(BASE).json()
    assert {r["key"] for r in rows} == set(mt.TEMPLATES)
    assert all(r["edited"] is False for r in rows)


def test_one_template_comes_with_its_variables_and_defaults(admin_client):
    one = admin_client.get(f"{BASE}/account_approved").json()
    assert one["body"] == one["default_body"]
    assert [v["name"] for v in one["variables"]] == ["login_url"]
    assert one["variables"][0]["must_appear"] is True and one["variables"][0]["is_required"]


def test_editing_saves_history_and_is_audited(admin_client):
    done = admin_client.put(f"{BASE}/account_approved", body(), format="json")
    assert done.status_code == 200 and done.json()["edited"] and done.json()["version"] == 2
    versions = admin_client.get(f"{BASE}/account_approved/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert AuditLog.objects.filter(action="email.template_edited").count() == 1


def test_bad_wording_is_refused_with_the_reason(admin_client):
    for fields, word in (
        ({"body": "no link"}, "must keep"),
        ({"subject": "WIN BIG NOW"}, "capital"),
        ({"body": "<b>x</b> [button: Go | {{login_url}}]"}, "HTML"),
    ):
        response = admin_client.put(f"{BASE}/account_approved", body(**fields), format="json")
        assert response.status_code == 400
        assert word in str(response.json())


def test_preview_shows_the_draft_without_saving(admin_client):
    draft = admin_client.post(
        f"{BASE}/account_approved/preview", {"subject": "Draft subject"}, format="json"
    ).json()
    assert draft["subject"] == "Draft subject" and "<table" in draft["html"]
    assert "Best regards," in draft["text"]
    assert admin_client.get(f"{BASE}/account_approved").json()["edited"] is False
    bad = admin_client.post(f"{BASE}/account_approved/preview", {"body": "x"}, format="json")
    assert bad.status_code == 400


def test_send_test_goes_only_to_the_admin(admin_client):
    done = admin_client.post(f"{BASE}/account_approved/test", {}, format="json")
    assert done.status_code == 204
    [sent] = FakeEmailAdapter.sent
    assert sent.to == "mod@example.com" and sent.subject.startswith("[Test] ")
    assert sent.html_body and sent.text_body


def test_restore_and_reset(admin_client):
    admin_client.put(f"{BASE}/account_approved", body(), format="json")
    restored = admin_client.post(f"{BASE}/account_approved/restore", {"version": 1}, format="json")
    assert restored.status_code == 200 and restored.json()["version"] == 3
    assert restored.json()["subject"] == restored.json()["default_subject"]
    reset = admin_client.post(f"{BASE}/account_approved/reset").json()
    assert reset["edited"] is False
    assert (
        admin_client.post(
            f"{BASE}/account_approved/restore", {"version": 99}, format="json"
        ).status_code
        == 404
    )


def test_unknown_template_is_404(admin_client):
    assert admin_client.get(f"{BASE}/nope").status_code == 404


def test_only_admins_with_the_permission_can_use_it(make_user, client_for, api_client):
    editor = client_for(make_user(roles=("content_editor",)), mfa_age=5)
    member = client_for(make_user())
    for client, expected in ((api_client, 401), (member, 403), (editor, 403)):
        assert client.get(BASE).status_code == expected
        assert client.put(f"{BASE}/welcome", body(), format="json").status_code == expected
        assert client.post(f"{BASE}/welcome/test", {}, format="json").status_code == expected
