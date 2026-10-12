import io
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from apps.analytics.models import AnalyticsEvent
from apps.integrations.storage import MEDIA, PRIVATE, get_storage
from apps.learning import certificates
from apps.learning.models import Certificate, CertificateSettings, Enrolment
from apps.learning.pdf import COLOURS, CertificateContent, render_certificate
from apps.learning.tests.conftest import build_course, lesson_ids
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

CERTS = "/api/v1/certificates"
VERIFY = "/api/v1/public/certificates"
NUMBER = re.compile(r"WO-C-\d{4}-\d{6}")


def finish(client, course):
    client.post(f"/api/v1/courses/{course.pk}/enrol")
    for lesson in lesson_ids(course):
        client.put(f"/api/v1/lessons/{lesson}/progress", {"completed": True}, format="json")


def set_name(user, name):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    FounderProfile.objects.filter(pk=get_or_create_profile(user.pk).pk).update(full_name=name)


@pytest.fixture
def certified(course, learner, learner_client, run_outbox):
    set_name(learner, "Ada Obi")
    finish(learner_client, course)
    run_outbox()
    return Certificate.objects.get()


def sample(**overrides):
    values = {
        "holder": "Ada Obi",
        "course": "Fundraising basics",
        "issued_at": datetime(2026, 10, 10, tzinfo=UTC),
        "number": "WO-C-2026-000341",
        "hours": Decimal("4.5"),
        "verify_url": "https://app.test/verify/WO-C-2026-000341",
    }
    values.update(overrides)
    return CertificateContent(**values)


# --- issuing ---


def test_completing_a_course_issues_a_certificate_through_a_worker(
    course, learner, learner_client, run_outbox
):
    set_name(learner, "Ada Obi")
    finish(learner_client, course)
    assert Certificate.objects.count() == 0  # made by a worker, not in the request
    run_outbox()
    certificate = Certificate.objects.get()
    assert certificate.holder_name == "Ada Obi" and certificate.course_title == "Fundraising basics"
    assert NUMBER.fullmatch(certificate.code)
    assert certificate.code.split("-")[2] == str(certificate.issued_at.year)
    assert certificate.enrolment.user_id == learner.pk
    assert certificate.hours == Decimal("0.1")  # five minutes of video, rounded to a tenth
    assert certificate.revoked_at is None and certificate.is_valid


def test_the_pdf_is_drawn_and_kept_privately_when_the_certificate_is_issued(certified):
    assert certified.pdf_key.startswith(f"certificates/{certified.pk}-")
    stored = get_storage().head(bucket=PRIVATE, key=certified.pdf_key)
    assert stored is not None and stored.content_type == "application/pdf"


def test_issuing_is_recorded_for_analytics(certified):
    event = AnalyticsEvent.objects.get(name="certificate_issued")
    assert event.properties == {"course_id": certified.enrolment.course.slug}


def test_the_certificate_keeps_the_template_it_was_issued_with(
    course, learner, learner_client, run_outbox, editor
):
    row = certificates.current_settings()
    row.signatory_name, row.signatory_title = "Onyeka Obi", "Founder"
    row.save()
    set_name(learner, "Ada Obi")
    finish(learner_client, course)
    run_outbox()
    certificate = Certificate.objects.get()
    row.signatory_name = "Someone New"
    row.version += 1
    row.save()
    one = learner_client.get(f"{CERTS}/{certificate.pk}").json()
    assert one["signatory_name"] == "Onyeka Obi" and one["signatory_title"] == "Founder"
    assert one["title_text"] == "Certificate of completion"


def test_running_the_worker_again_makes_no_second_certificate_or_notice(
    certified, learner, run_outbox
):
    from apps.core.models import OutboxEvent

    OutboxEvent.objects.update(status="pending")
    run_outbox()
    assert Certificate.objects.count() == 1
    assert Notification.objects.filter(user=learner, type="certificate_ready").count() == 1
    assert certificates.issue(certified.enrolment_id).pk == certified.pk


def test_the_member_is_told_their_certificate_is_ready(certified, learner_client):
    [item] = learner_client.get("/api/v1/notifications").json()["results"]
    assert item["type"] == "certificate_ready"
    assert item["link"] == f"/learn/certificates/{certified.pk}"
    assert "Fundraising basics" in item["title"]


def test_courses_can_switch_certificates_off(editor, learner_client, run_outbox):
    plain_course = build_course(editor, certificate_enabled=False)
    finish(learner_client, plain_course)
    run_outbox()
    assert Certificate.objects.count() == 0
    assert Enrolment.objects.get().completed_at is not None  # the course still counts as done


def test_an_unfinished_course_gets_no_certificate(course, learner_client, run_outbox):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    learner_client.put(
        f"/api/v1/lessons/{lesson_ids(course)[0]}/progress", {"completed": True}, format="json"
    )
    run_outbox()
    assert Certificate.objects.count() == 0
    assert certificates.issue(Enrolment.objects.get().pk) is None


def test_a_name_change_later_does_not_alter_the_certificate(certified, learner):
    set_name(learner, "Someone Else")
    certified.refresh_from_db()
    assert certified.holder_name == "Ada Obi"


def test_a_member_without_a_profile_name_still_gets_a_certificate(
    course, learner_client, run_outbox
):
    finish(learner_client, course)
    run_outbox()
    assert Certificate.objects.get().holder_name == "WO Community member"


def test_a_failed_drawing_does_not_undo_the_certificate(
    course, learner, learner_client, run_outbox, monkeypatch
):
    def broken(_certificate):
        raise RuntimeError("storage is down")

    monkeypatch.setattr(certificates, "store_pdf", broken)
    set_name(learner, "Ada Obi")
    finish(learner_client, course)
    run_outbox()
    certificate = Certificate.objects.get()
    assert certificate.pdf_key == ""
    monkeypatch.undo()
    assert learner_client.get(f"{CERTS}/{certificate.pk}/download").status_code == 200  # drawn now


# --- viewing and downloading ---


def test_a_member_lists_and_opens_their_certificates(certified, learner_client):
    for path in (CERTS, "/api/v1/me/certificates"):
        [listed] = learner_client.get(path).json()
        assert listed["number"] == certified.code and listed["holder_name"] == "Ada Obi"
        assert listed["status"] == "valid" and listed["hours"] == 0.1
    one = learner_client.get(f"{CERTS}/{certified.pk}").json()
    assert one["id"] == str(certified.pk)
    assert one["verify_url"] == f"https://app.test/verify/{certified.code}"


def test_the_download_is_a_short_lived_link_to_a_valid_pdf(certified, learner_client):
    response = learner_client.get(f"{CERTS}/{certified.pk}/download")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    body = response.json()
    assert body["filename"] == f"certificate-{certified.code}.pdf" and body["expires_in"] > 0
    assert body["url"].startswith("https://") and certified.pdf_key in body["url"]
    data, _ = get_storage().objects[(PRIVATE, certified.pdf_key)]
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    event = AnalyticsEvent.objects.get(name="certificate_downloaded")
    assert event.properties == {"course_id": certified.enrolment.course.slug}


def test_certificates_belong_to_their_owner(certified, other_client, api_client):
    assert other_client.get(f"{CERTS}/{certified.pk}").status_code == 404
    assert other_client.get(f"{CERTS}/{certified.pk}/download").status_code == 404
    assert other_client.get(CERTS).json() == []
    assert api_client.get(f"{CERTS}/{certified.pk}").status_code == 401
    assert api_client.get(f"{CERTS}/{certified.pk}/download").status_code == 401
    assert api_client.get(CERTS).status_code == 401
    assert api_client.get("/api/v1/me/certificates").status_code == 401


def test_unknown_certificates_are_404(learner_client):
    assert learner_client.get(f"{CERTS}/{uuid.uuid4()}").status_code == 404
    assert learner_client.get(f"{CERTS}/{uuid.uuid4()}/download").status_code == 404


def test_a_revoked_certificate_cannot_be_downloaded(certified, learner_client, editor):
    certificates.revoke(actor=editor, certificate_id=certified.pk, reason="Issued in error")
    assert learner_client.get(f"{CERTS}/{certified.pk}/download").status_code == 409
    [listed] = learner_client.get(CERTS).json()
    assert listed["status"] == "revoked"


# --- verifying ---


def test_anyone_can_verify_a_number_without_logging_in(certified, api_client):
    body = api_client.get(f"{VERIFY}/{certified.code}").json()
    assert body["valid"] is True and body["status"] == "valid"
    assert body["holder_name"] == "Ada Obi" and body["course_title"] == "Fundraising basics"
    assert body["number"] == certified.code and "id" not in body
    assert api_client.get(f"{VERIFY}/{certified.code.lower()}").status_code == 200
    assert "public" in api_client.get(f"{VERIFY}/{certified.code}")["Cache-Control"]


def test_a_revoked_certificate_is_shown_as_revoked_and_nothing_more(certified, api_client, editor):
    certificates.revoke(actor=editor, certificate_id=certified.pk, reason="Issued in error")
    body = api_client.get(f"{VERIFY}/{certified.code}").json()
    assert body["valid"] is False and body["status"] == "revoked"
    assert body["holder_name"] == "" and body["course_title"] == "" and body["issued_at"] is None
    assert "Issued in error" not in str(body)


@pytest.mark.parametrize(
    "code", ["WO-C-2026-999999", "short", "x" * 40, "..%2F..", "'; DROP TABLE"]
)
def test_unknown_numbers_are_404(api_client, code):
    assert api_client.get(f"{VERIFY}/{code}").status_code == 404


def test_verification_exposes_no_contact_details(certified, api_client):
    text = api_client.get(f"{VERIFY}/{certified.code}").content.decode()
    assert "learner@example.com" not in text and str(certified.enrolment.user_id) not in text


def test_older_certificates_keep_their_short_code(certified, api_client):
    Certificate.objects.filter(pk=certified.pk).update(code="ABCDEFGH2345")
    assert api_client.get(f"{VERIFY}/ABCDEFGH2345").json()["valid"] is True


# --- the PDF itself ---


def test_the_pdf_is_one_a4_landscape_page_with_embedded_fonts_and_a_small_size():
    pdf = render_certificate(sample())
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF") and pdf.count(b"%%EOF") == 1
    assert re.search(rb"/MediaBox \[ ?0 0 842 595 ?\]", pdf)  # 297 by 210 mm
    assert len(re.findall(rb"/Type /Page\b(?!s)", pdf)) == 1
    assert b"/FontFile2" in pdf and b"/ToUnicode" in pdf  # embedded, and the text can be selected
    assert len(pdf) < 500 * 1024


def test_unusual_characters_and_long_text_do_not_break_the_file():
    pdf = render_certificate(
        sample(
            holder="Ọlákúnlé Adébáyọ̀ Ṣola 李 (the) \\ Obi",
            course="C" * 300,
            signatory_name="S" * 120,
            signatory_title="T" * 120,
        )
    )
    assert pdf.startswith(b"%PDF-") and len(pdf) < 500 * 1024
    assert pdf.count(b"%%EOF") == 1


def test_a_signature_image_is_placed_on_the_page():
    image = io.BytesIO()
    Image.new("RGBA", (200, 60), (6, 55, 47, 255)).save(image, "PNG")
    plain_pdf = render_certificate(sample())
    signed = render_certificate(sample(signature_png=image.getvalue(), signatory_name="Onyeka"))
    assert b"/Subtype /Image" in signed and b"/Subtype /Image" not in plain_pdf


def test_the_colours_are_the_design_tokens():
    tokens = (Path(__file__).parents[3] / "frontend/src/styles/tokens.css").read_text("utf8")
    for name, value in COLOURS.items():
        found = re.search(rf"--{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", tokens)
        if found:  # a few are named only in print (text-secondary has a dark value too)
            assert found.group(1).upper() == value.upper(), name


def test_a_stored_signature_appears_on_new_certificates(
    course, learner, learner_client, run_outbox, editor
):
    image = io.BytesIO()
    Image.new("RGBA", (200, 60), (6, 55, 47, 255)).save(image, "WEBP")
    get_storage().write(
        bucket=MEDIA,
        key="media/cert_signature/abc/large.webp",
        data=image.getvalue(),
        content_type="image/webp",
    )
    row = certificates.current_settings()
    row.signature_key = "media/cert_signature/abc"
    row.signatory_name = "Onyeka Obi"
    row.save()
    set_name(learner, "Ada Obi")
    finish(learner_client, course)
    run_outbox()
    certificate = Certificate.objects.get()
    data, _ = get_storage().objects[(PRIVATE, certificate.pdf_key)]
    assert b"/Subtype /Image" in data
    assert CertificateSettings.objects.count() == 1
