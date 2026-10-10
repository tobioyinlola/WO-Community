import re
import uuid
from datetime import UTC, datetime

import pytest

from apps.learning import learn
from apps.learning.models import Certificate, Enrolment
from apps.learning.pdf import render_certificate
from apps.learning.tests.conftest import build_course, lesson_ids
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

CERTS = "/api/v1/certificates"
VERIFY = "/api/v1/public/certificates"


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
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{12}", certificate.code)
    assert certificate.enrolment.user_id == learner.pk


def test_running_the_worker_again_makes_no_second_certificate_or_notice(
    certified, learner, run_outbox
):
    from apps.core.models import OutboxEvent

    OutboxEvent.objects.update(status="pending")
    run_outbox()
    assert Certificate.objects.count() == 1
    assert Notification.objects.filter(user=learner, type="certificate_ready").count() == 1
    assert learn.issue_certificate(certified.enrolment_id).pk == certified.pk


def test_the_member_is_told_their_certificate_is_ready(certified, learner_client):
    [item] = learner_client.get("/api/v1/notifications").json()["results"]
    assert item["type"] == "certificate_ready" and item["link"] == f"/certificates/{certified.pk}"
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
    assert learn.issue_certificate(Enrolment.objects.get().pk) is None


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


# --- viewing and downloading ---


def test_a_member_lists_and_opens_their_certificates(certified, learner_client):
    [listed] = learner_client.get(CERTS).json()
    assert listed["code"] == certified.code and listed["holder_name"] == "Ada Obi"
    one = learner_client.get(f"{CERTS}/{certified.pk}").json()
    assert one["id"] == str(certified.pk) and one["verify_url"].endswith(
        f"/verify/{certified.code}"
    )


def test_the_pdf_is_a_valid_download(certified, learner_client):
    response = learner_client.get(f"{CERTS}/{certified.pk}/pdf")
    assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
    assert (
        response["Content-Disposition"]
        == f'attachment; filename="certificate-{certified.code}.pdf"'
    )
    assert response["Cache-Control"] == "private, no-store"
    body = response.content
    assert body.startswith(b"%PDF-1.4") and body.rstrip().endswith(b"%%EOF")
    assert b"Ada Obi" in body and certified.code.encode() in body and b"Fundraising basics" in body


def test_certificates_belong_to_their_owner(certified, other_client, api_client):
    assert other_client.get(f"{CERTS}/{certified.pk}").status_code == 404
    assert other_client.get(f"{CERTS}/{certified.pk}/pdf").status_code == 404
    assert other_client.get(CERTS).json() == []
    assert api_client.get(f"{CERTS}/{certified.pk}").status_code == 401
    assert api_client.get(CERTS).status_code == 401


def test_unknown_certificates_are_404(learner_client):
    assert learner_client.get(f"{CERTS}/{uuid.uuid4()}").status_code == 404


# --- verifying ---


def test_anyone_can_verify_a_code_without_logging_in(certified, api_client):
    body = api_client.get(f"{VERIFY}/{certified.code}").json()
    assert body["valid"] is True and body["holder_name"] == "Ada Obi"
    assert body["course_title"] == "Fundraising basics" and "id" not in body
    assert (
        api_client.get(f"{VERIFY}/{certified.code.lower()}").status_code == 200
    )  # typed in lower case
    assert "public" in api_client.get(f"{VERIFY}/{certified.code}")["Cache-Control"]


@pytest.mark.parametrize("code", ["ZZZZZZZZZZZZ", "short", "x" * 40, "..%2F..", "'; DROP TABLE"])
def test_unknown_codes_are_404(api_client, code):
    assert api_client.get(f"{VERIFY}/{code}").status_code == 404


def test_verification_exposes_no_contact_details(certified, api_client):
    text = api_client.get(f"{VERIFY}/{certified.code}").content.decode()
    assert "learner@example.com" not in text and str(certified.enrolment.user_id) not in text


# --- the PDF itself ---


def test_the_pdf_structure_is_sound():
    pdf = render_certificate(
        holder="Ada Obi",
        course="Fundraising basics",
        issued_at=datetime(2026, 10, 10, tzinfo=UTC),
        code="ABCDEFGH2345",
        verify_url="https://app.test/verify/ABCDEFGH2345",
    )
    start = int(re.search(rb"startxref\n(\d+)\n", pdf).group(1))
    assert pdf[start : start + 4] == b"xref"
    offsets = [int(m) for m in re.findall(rb"(\d{10}) 00000 n", pdf)]
    for number, offset in enumerate(offsets, start=1):
        assert pdf[offset:].startswith(b"%d 0 obj" % number)
    assert b"Issued 10 October 2026" in pdf


def test_text_is_escaped_and_unusual_characters_do_not_break_the_file():
    pdf = render_certificate(
        holder="Ada (the) \\ Obi 李 Zoë",
        course="Course ) /Type /Catalog (",
        issued_at=datetime(2026, 1, 1, tzinfo=UTC),
        code="ABCDEFGH2345",
        verify_url="https://app.test/verify/x",
    )
    assert b"Ada \\(the\\) \\\\ Obi ? Zo\xeb" in pdf  # brackets escaped, Latin-1 kept, others "?"
    assert b"Course \\) /Type /Catalog \\(" in pdf
    assert pdf.count(b"%%EOF") == 1 and pdf.rstrip().endswith(b"%%EOF")


def test_very_long_names_are_shortened():
    pdf = render_certificate(
        holder="N" * 200,
        course="C" * 300,
        issued_at=datetime(2026, 1, 1, tzinfo=UTC),
        code="ABCDEFGH2345",
        verify_url="https://app.test/verify/x",
    )
    assert b"N" * 61 not in pdf and b"C" * 71 not in pdf
