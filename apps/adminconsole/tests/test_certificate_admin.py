import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.integrations.storage import PRIVATE, get_storage
from apps.learning import certificates
from apps.learning.models import Certificate, CertificateSettings
from apps.learning.tests.conftest import build_course, lesson_ids
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin"
NIL = "00000000-0000-0000-0000-000000000001"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def as_editor(editor, client_for):
    return client_for(editor, mfa_age=5)


@pytest.fixture
def learner(make_user):
    return active(make_user, "learner@example.com")


@pytest.fixture
def learner_client(learner, client_for):
    return client_for(learner)


@pytest.fixture
def certified(editor, learner, learner_client, run_outbox):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    FounderProfile.objects.filter(pk=get_or_create_profile(learner.pk).pk).update(
        full_name="Ada Obi"
    )
    course = build_course(editor)
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    for lesson in lesson_ids(course):
        learner_client.put(f"/api/v1/lessons/{lesson}/progress", {"completed": True}, format="json")
    run_outbox()
    return Certificate.objects.get()


def call(client, method, path, payload=None):
    send = getattr(client, method)
    return send(path, payload, format="json") if payload is not None else send(path)


ENDPOINTS = [
    ("get", f"{ADMIN}/certificate-settings", None),
    ("put", f"{ADMIN}/certificate-settings", {"signatory_name": "Onyeka Obi"}),
    ("post", f"{ADMIN}/certificate-settings/preview", {}),
    ("get", f"{ADMIN}/certificates", None),
    ("post", f"{ADMIN}/certificates/{NIL}/revoke", {"reason": "Issued in error"}),
    ("post", f"{ADMIN}/certificates/{NIL}/reissue", {}),
]


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_signing_in_is_required(api_client, method, path, payload):
    assert call(api_client, method, path, payload).status_code == 401


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_an_ordinary_member_is_refused(learner, client_for, method, path, payload):
    assert call(client_for(learner, mfa_age=5), method, path, payload).status_code == 403


@pytest.mark.parametrize("method,path,payload", ENDPOINTS)
def test_an_editor_without_the_second_step_is_refused(editor, client_for, method, path, payload):
    assert call(client_for(editor), method, path, payload).status_code == 403


@pytest.mark.parametrize("method,path,payload", ENDPOINTS[4:])
def test_an_unknown_certificate_is_not_found(as_editor, method, path, payload):
    assert call(as_editor, method, path, payload).status_code == 404


# --- the template ---


def test_the_settings_start_with_sensible_defaults(as_editor):
    body = as_editor.get(f"{ADMIN}/certificate-settings").json()
    assert (
        body["title_text"] == "Certificate of completion"
        and body["signatory_name"] == "Onyeka Akumah"
    )
    assert body["signature_url"] is None and body["version"] == 1
    assert CertificateSettings.objects.count() == 1


def test_settings_are_saved_and_audited(as_editor):
    response = as_editor.put(
        f"{ADMIN}/certificate-settings",
        {
            "title_text": "Certificate of achievement",
            "signatory_name": " Onyeka Obi ",
            "signatory_title": "Founder",
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title_text"] == "Certificate of achievement"
    assert body["signatory_name"] == "Onyeka Obi" and body["version"] == 2
    assert as_editor.get(f"{ADMIN}/certificate-settings").json()["signatory_title"] == "Founder"
    entry = AuditLog.objects.get(action="certificates.template_changed")
    assert entry.after["signatory_name"] == "Onyeka Obi"


@pytest.mark.parametrize(
    "payload",
    [
        {"title_text": ""},
        {"title_text": "x" * 61},
        {"signatory_name": "x" * 121},
        {"signature_upload_id": "not-a-uuid"},
        {"colour": "red"},
    ],
)
def test_bad_settings_are_refused(as_editor, payload):
    assert as_editor.put(f"{ADMIN}/certificate-settings", payload, format="json").status_code == 400
    assert certificates.current_settings().version == 1


def test_an_unknown_signature_upload_is_refused(as_editor):
    response = as_editor.put(
        f"{ADMIN}/certificate-settings", {"signature_upload_id": NIL}, format="json"
    )
    assert response.status_code == 400 and "upload_id" in str(response.json())


def test_markup_in_the_template_text_is_stripped(as_editor):
    body = as_editor.put(
        f"{ADMIN}/certificate-settings",
        {"signatory_name": "<b>Onyeka</b><script>x()</script>"},
        format="json",
    ).json()
    assert "<" not in body["signatory_name"]


def test_the_preview_draws_a_pdf_and_saves_nothing(as_editor):
    response = as_editor.post(
        f"{ADMIN}/certificate-settings/preview",
        {"signatory_name": "Preview Person", "title_text": "Certificate of merit"},
        format="json",
    )
    assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
    assert (
        response.content.startswith(b"%PDF-") and response["Cache-Control"] == "private, no-store"
    )
    row = certificates.current_settings()
    assert row.signatory_name == "Onyeka Akumah" and row.version == 1


def test_a_bad_preview_is_refused(as_editor):
    assert (
        as_editor.post(f"{ADMIN}/certificate-settings/preview", {"x": 1}, format="json").status_code
        == 400
    )


# --- the list ---


def test_certificates_are_listed_and_searched(as_editor, certified):
    body = as_editor.get(f"{ADMIN}/certificates").json()
    assert body["count"] == 1
    [row] = body["results"]
    assert row["number"] == certified.code and row["email"] == "learner@example.com"
    assert row["status"] == "valid" and row["template_version"] == 1
    assert as_editor.get(f"{ADMIN}/certificates", {"q": "ada"}).json()["count"] == 1
    assert as_editor.get(f"{ADMIN}/certificates", {"q": "nobody"}).json()["count"] == 0
    assert as_editor.get(f"{ADMIN}/certificates", {"status": "revoked"}).json()["count"] == 0
    assert as_editor.get(f"{ADMIN}/certificates", {"status": "nonsense"}).status_code == 400


# --- revoking ---


def test_revoking_needs_a_reason(as_editor, certified):
    for payload in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 301}):
        response = as_editor.post(
            f"{ADMIN}/certificates/{certified.pk}/revoke", payload, format="json"
        )
        assert response.status_code == 400
    certified.refresh_from_db()
    assert certified.revoked_at is None


def test_a_certificate_is_revoked_once_and_the_public_page_says_so(
    as_editor, certified, api_client, learner_client
):
    response = as_editor.post(
        f"{ADMIN}/certificates/{certified.pk}/revoke", {"reason": "Issued in error"}, format="json"
    )
    assert response.status_code == 200
    assert (
        response.json()["status"] == "revoked"
        and response.json()["revoked_reason"] == "Issued in error"
    )
    assert AuditLog.objects.filter(action="certificates.revoked", reason="Issued in error").exists()
    assert api_client.get(f"/api/v1/public/certificates/{certified.code}").json()["valid"] is False
    assert learner_client.get(f"/api/v1/certificates/{certified.pk}/download").status_code == 409
    again = as_editor.post(
        f"{ADMIN}/certificates/{certified.pk}/revoke", {"reason": "Twice"}, format="json"
    )
    assert again.status_code == 409
    assert as_editor.get(f"{ADMIN}/certificates", {"status": "revoked"}).json()["count"] == 1


# --- reissuing ---


def test_reissuing_draws_it_again_with_the_current_template_and_keeps_the_number(
    as_editor, certified, learner
):
    old_key = certified.pdf_key
    as_editor.put(f"{ADMIN}/certificate-settings", {"signatory_name": "Onyeka Obi"}, format="json")
    response = as_editor.post(f"{ADMIN}/certificates/{certified.pk}/reissue", {}, format="json")
    assert response.status_code == 200
    certified.refresh_from_db()
    assert response.json()["number"] == certified.code and response.json()["template_version"] == 2
    assert certified.template["signatory_name"] == "Onyeka Obi"
    assert certified.pdf_key != old_key
    assert get_storage().head(bucket=PRIVATE, key=old_key) is None  # the old file is gone
    assert get_storage().head(bucket=PRIVATE, key=certified.pdf_key) is not None
    assert AuditLog.objects.filter(action="certificates.reissued").exists()
    assert Notification.objects.filter(user=learner, type="certificate_ready").count() == 2


def test_the_name_can_be_corrected_when_reissuing(as_editor, certified):
    response = as_editor.post(
        f"{ADMIN}/certificates/{certified.pk}/reissue", {"holder_name": "Adaeze Obi"}, format="json"
    )
    assert response.status_code == 200 and response.json()["holder_name"] == "Adaeze Obi"
    certified.refresh_from_db()
    assert certified.holder_name == "Adaeze Obi"


@pytest.mark.parametrize("payload", [{"holder_name": "   "}, {"holder_name": "x" * 161}, {"x": 1}])
def test_a_bad_reissue_is_refused(as_editor, certified, payload):
    response = as_editor.post(
        f"{ADMIN}/certificates/{certified.pk}/reissue", payload, format="json"
    )
    assert response.status_code == 400


def test_reissuing_a_revoked_certificate_makes_it_valid_again(
    as_editor, certified, api_client, learner_client
):
    as_editor.post(
        f"{ADMIN}/certificates/{certified.pk}/revoke", {"reason": "Issued in error"}, format="json"
    )
    assert api_client.get(f"/api/v1/public/certificates/{certified.code}").json()["valid"] is False
    response = as_editor.post(f"{ADMIN}/certificates/{certified.pk}/reissue", {}, format="json")
    assert response.status_code == 200
    assert response.json()["status"] == "valid" and response.json()["revoked_reason"] == ""
    assert api_client.get(f"/api/v1/public/certificates/{certified.code}").json()["valid"] is True
    assert learner_client.get(f"/api/v1/certificates/{certified.pk}/download").status_code == 200
    entry = AuditLog.objects.filter(action="certificates.reissued").latest("created_at")
    assert entry.before["revoked"] is True and entry.after["revoked"] is False
