import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db

MEMBERS = "/api/v1/admin/members"


@pytest.fixture
def admin_client(make_user, client_for):
    admin = make_user(roles=("community_admin",), email="admin@example.com")
    return client_for(admin, mfa_age=5)


@pytest.fixture
def member(make_user):
    return make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


def subjects(sent):
    return [(m.to, m.subject) for m in sent]


def test_a_suspended_member_is_told_why(admin_client, member, run_outbox, sent_emails):
    response = admin_client.post(
        f"{MEMBERS}/{member.pk}/suspend", {"reason": "Repeated spam in comments"}, format="json"
    )
    assert response.status_code == 200
    run_outbox()
    mail = [m for m in sent_emails if m.to == member.email]
    assert [m.subject for m in mail] == ["Your WO Community account has been suspended"]
    assert "Repeated spam in comments" in mail[0].text_body
    assert "mentoring sessions" in mail[0].text_body


def test_a_reinstated_member_is_told(admin_client, member, run_outbox, sent_emails):
    admin_client.post(f"{MEMBERS}/{member.pk}/suspend", {"reason": "Spam"}, format="json")
    run_outbox()
    admin_client.post(f"{MEMBERS}/{member.pk}/reinstate")
    run_outbox()
    last = [m for m in sent_emails if m.to == member.email][-1]
    assert last.subject == "Your WO Community account is active again"
    assert "/login" in last.text_body


def test_a_removed_member_is_told_why(admin_client, member, run_outbox, sent_emails):
    admin_client.post(f"{MEMBERS}/{member.pk}/remove", {"reason": "Fake startup"}, format="json")
    run_outbox()
    mail = [m for m in sent_emails if m.to == member.email]
    assert [m.subject for m in mail] == ["Your WO Community account has been removed"]
    assert "Fake startup" in mail[0].text_body


def test_a_changed_password_is_confirmed_by_email(member, run_outbox, sent_emails):
    from apps.accounts import services as accounts

    _, token = accounts.issue_email_token(member.pk, accounts.PASSWORD_RESET)
    accounts.reset_password(raw_token=token, new_password="A-new-long-passphrase-2026")
    run_outbox()
    mail = [m for m in sent_emails if m.subject == "Your WO Community password was changed"]
    assert [m.to for m in mail] == [member.email]
    assert "(UTC)" in mail[0].text_body and "/forgot-password" in mail[0].text_body


def test_an_applicant_hears_their_application_arrived(make_user, run_outbox, sent_emails):
    from apps.accounts import services as accounts

    applicant = make_user(email="new@example.com", status="pending", email_verified_at=None)
    _, token = accounts.issue_email_token(applicant.pk, accounts.VERIFY_EMAIL)
    accounts.verify_email(token)
    run_outbox()
    mail = [m for m in sent_emails if m.to == applicant.email]
    assert [m.subject for m in mail] == ["We've got your application, there"]
    assert "3 to 5 working days" in mail[0].text_body
