from datetime import timedelta

import pytest
from django.utils import timezone

from apps.integrations.email.fake import FakeEmailAdapter
from apps.notifications import adminalerts
from apps.notifications.models import AdminAlert, AdminAlertPreference, Notification

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_sent():
    FakeEmailAdapter.reset()


@pytest.fixture
def admin(make_user):
    return make_user(
        roles=("community_admin",),
        email="admin@example.com",
        approved_at=timezone.now(),
        email_verified_at=timezone.now(),
    )


def raise_one(n=1, kind="member_signup", **fields):
    return adminalerts.raise_alert(
        kind,
        item_key=f"test:{kind}:{n}",
        what=f"Request {n}",
        who=f"person{n}@example.com",
        path=f"/admin/members/{n}",
        **fields,
    )


def mails():
    return [m for m in FakeEmailAdapter.sent if m.to == "admin@example.com"]


def test_the_first_item_is_emailed_at_once_with_one_review_button(admin):
    raise_one(1)
    assert adminalerts.dispatch("member_signup") == 1
    [mail] = mails()
    assert "Request 1" in mail.text_body and "person1@example.com" in mail.text_body
    assert "/admin/members/1" in mail.text_body and "Review request" in mail.html_body
    assert mail.html_body.count("Review request") == 1
    assert "Best regards," in mail.text_body


def test_more_items_within_fifteen_minutes_wait_and_then_go_as_one_digest(admin):
    raise_one(1)
    adminalerts.dispatch("member_signup")
    raise_one(2)
    raise_one(3)
    assert adminalerts.dispatch("member_signup") == 0  # inside the window
    assert len(mails()) == 1
    later = timezone.now() + timedelta(minutes=16)
    assert adminalerts.dispatch("member_signup", now=later) == 1
    digest = mails()[1]
    assert digest.subject == "2 items waiting for your review"
    assert "Request 2" in digest.text_body and "Request 3" in digest.text_body
    # Nothing is sent twice.
    assert adminalerts.dispatch("member_signup", now=later + timedelta(hours=1)) == 0


def test_an_item_is_recorded_and_sent_once_however_often_it_is_raised(admin):
    assert raise_one(1) is True
    assert raise_one(1) is False
    assert AdminAlert.objects.count() == 1
    adminalerts.dispatch("member_signup")
    adminalerts.dispatch("member_signup")
    assert len(mails()) == 1


def test_only_admins_who_may_approve_that_kind_are_told(admin, make_user):
    editor = make_user(roles=("content_editor",), email="editor@example.com")
    raise_one(1, kind="member_signup")  # needs members.approve: the editor lacks it
    adminalerts.dispatch("member_signup")
    assert [m.to for m in FakeEmailAdapter.sent] == ["admin@example.com"]
    raise_one(2, kind="job_pending")  # jobs.moderate: both have it
    adminalerts.dispatch("job_pending")
    assert {m.to for m in FakeEmailAdapter.sent} == {"admin@example.com", editor.email}


def test_an_admin_can_switch_a_kind_off(admin):
    AdminAlertPreference.objects.create(user=admin, kind="member_signup", enabled=False)
    raise_one(1)
    assert adminalerts.dispatch("member_signup") == 0
    assert mails() == []
    assert adminalerts.recipients("member_signup") == []


def test_in_app_notifications_are_made_once_per_item(admin):
    raise_one(1)
    alert = AdminAlert.objects.get()
    assert adminalerts.deliver_in_app(alert.pk) == 1
    assert adminalerts.deliver_in_app(alert.pk) == 0
    note = Notification.objects.get(user=admin)
    assert note.type == "admin_attention" and note.payload["path"] == "/admin/members/1"


def test_kinds_that_already_notify_in_app_do_not_repeat_it(admin):
    raise_one(1, kind="support_ticket", in_app=False)
    assert adminalerts.deliver_in_app(AdminAlert.objects.get().pk) == 0
