import io
import zipfile

import pytest

from apps.integrations.malware.fake import EICAR
from apps.integrations.storage.base import PRIVATE, QUARANTINE
from apps.integrations.storage.fake import FakeStorage
from apps.uploads import documents
from apps.uploads.documents import DocumentRejected
from apps.uploads.models import Upload

pytestmark = pytest.mark.django_db

UPLOADS = "/api/v1/uploads"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def pdf_bytes(extra: bytes = b"") -> bytes:
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R "
        + extra
        + b">>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )


def office_bytes(main="word/document.xml", extra: dict[str, bytes] | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(main, "<doc/>")
        for name, body in (extra or {}).items():
            archive.writestr(name, body)
    return out.getvalue()


# --- inspecting ---


def test_a_plain_pdf_and_office_files_pass():
    assert documents.inspect(pdf_bytes(), PDF).size > 0
    assert documents.inspect(office_bytes(), DOCX).content_type == DOCX
    assert documents.inspect(office_bytes("xl/workbook.xml"), XLSX).content_type == XLSX
    assert documents.inspect(office_bytes("ppt/presentation.xml"), PPTX).content_type == PPTX


@pytest.mark.parametrize(
    ("data", "declared", "code"),
    [
        (b"MZ\x90\x00 not a document", PDF, "type_mismatch"),
        (pdf_bytes(), DOCX, "type_mismatch"),
        (office_bytes(), PDF, "type_mismatch"),
        (office_bytes("xl/workbook.xml"), DOCX, "type_mismatch"),
        (b"%PDF-1.4 truncated", PDF, "corrupt"),
        (pdf_bytes(b"/JavaScript (app.alert(1))"), PDF, "active_content"),
        (pdf_bytes(b"/J#61vaScript (hidden)"), PDF, "active_content"),
        (pdf_bytes(b"/Launch << /F (cmd.exe) >>"), PDF, "active_content"),
        (pdf_bytes(b"/Encrypt 5 0 R"), PDF, "encrypted"),
        (office_bytes(extra={"word/vbaProject.bin": b"x"}), DOCX, "active_content"),
        (office_bytes(extra={"word/embeddings/oleObject1.bin": b"x"}), DOCX, "active_content"),
        (office_bytes(extra={"word/run.exe": b"x"}), DOCX, "active_content"),
        (office_bytes(), "text/html", "type_not_allowed"),
    ],
)
def test_documents_that_are_not_what_they_claim_or_carry_code_are_refused(data, declared, code):
    with pytest.raises(DocumentRejected) as caught:
        documents.inspect(data, declared)
    assert caught.value.code == code


def test_an_archive_bomb_is_refused(settings):
    settings.UPLOAD_DOCUMENT_MAX_UNPACKED_BYTES = 1000
    with pytest.raises(DocumentRejected) as caught:
        documents.inspect(office_bytes(extra={"word/media/huge.bin": b"0" * 5000}), DOCX)
    assert caught.value.code == "too_large_unpacked"


# --- the upload flow ---


@pytest.fixture
def editor_client(make_user, client_for):
    return client_for(make_user(roles=("content_editor",), email="editor@example.com"))


@pytest.fixture
def member_client(make_user, client_for):
    return client_for(make_user(email="member@example.com"))


def start(client, data, content_type=PDF, **overrides):
    body = {
        "purpose": "course_file",
        "content_type": content_type,
        "size": len(data),
        "filename": "Term sheet.pdf",
        **overrides,
    }
    return client.post(UPLOADS, body)


def send(created, data, content_type=PDF):
    form = created.json()["form"]["form_data"]
    from apps.integrations.storage.base import PresignedPost

    post = PresignedPost("https://storage.test/q", form, 900)
    FakeStorage.client_upload(post, data, content_type)


def run(client, run_outbox, data, content_type=PDF, **overrides):
    created = start(client, data, content_type, **overrides)
    assert created.status_code == 201, created.content
    send(created, data, content_type)
    upload_id = created.json()["upload"]["id"]
    assert client.post(f"{UPLOADS}/{upload_id}/complete").status_code == 202
    run_outbox()
    return Upload.objects.get(pk=upload_id)


def test_only_course_staff_may_upload_documents(member_client, api_client):
    assert start(member_client, pdf_bytes()).status_code == 403
    assert api_client.post(UPLOADS, {}).status_code == 401


def test_a_document_is_checked_then_kept_privately_and_unchanged(editor_client, run_outbox):
    data = pdf_bytes()
    upload = run(editor_client, run_outbox, data)
    assert upload.status == "ready" and upload.size == len(data)
    assert upload.base_key.startswith("private/course_file/")
    assert FakeStorage.objects[(PRIVATE, upload.base_key)] == (data, PDF)  # not re-encoded
    assert (QUARANTINE, upload.quarantine_key) not in FakeStorage.objects  # raw copy removed
    body = editor_client.get(f"{UPLOADS}/{upload.pk}").json()
    assert body["urls"] is None  # a document has no public address
    assert body["filename"] == "Term sheet.pdf" and body["size"] == len(data)


def test_office_files_are_accepted_too(editor_client, run_outbox):
    upload = run(editor_client, run_outbox, office_bytes(), DOCX, filename="Plan.docx")
    assert upload.status == "ready"


@pytest.mark.parametrize(
    ("data", "content_type", "reason"),
    [
        (pdf_bytes(b"/JavaScript (x)"), PDF, "active_content"),
        (b"%PDF-1.4 not really a pdf and no end marker", PDF, "corrupt"),
        (pdf_bytes(), DOCX, "type_mismatch"),
    ],
)
def test_bad_documents_are_rejected_with_a_reason(
    editor_client, run_outbox, data, content_type, reason
):
    upload = run(editor_client, run_outbox, data, content_type)
    assert upload.status == "rejected" and upload.reject_reason == reason
    assert not [k for k in FakeStorage.objects if k[0] == PRIVATE]


def test_a_document_with_a_virus_is_rejected(editor_client, run_outbox):
    upload = run(editor_client, run_outbox, pdf_bytes(EICAR))
    assert upload.status == "rejected" and upload.reject_reason == "malware_detected"
    assert not [k for k in FakeStorage.objects if k[0] == PRIVATE]


def test_documents_have_their_own_type_and_size_limits(editor_client, settings):
    assert start(editor_client, pdf_bytes(), "image/png").status_code == 400
    assert start(editor_client, pdf_bytes(), "application/zip").status_code == 400
    too_big = start(editor_client, b"x", PDF, size=settings.UPLOAD_DOCUMENT_MAX_BYTES + 1)
    assert too_big.status_code == 400
    # An image is still an image: a document type is refused for the photo purposes.
    refused = editor_client.post(
        UPLOADS, {"purpose": "profile_photo", "content_type": PDF, "size": 100}
    )
    assert refused.status_code == 400


def test_unused_documents_are_deleted_by_housekeeping(editor_client, run_outbox, settings):
    from datetime import timedelta

    from django.utils import timezone

    from apps.uploads import services

    upload = run(editor_client, run_outbox, pdf_bytes())
    Upload.objects.filter(pk=upload.pk).update(ready_at=timezone.now() - timedelta(days=2))
    assert services.cleanup()["discarded"] == 1
    assert (PRIVATE, upload.base_key) not in FakeStorage.objects


def test_download_links_are_short_lived_attachments(editor_client, run_outbox):
    from apps.uploads import services

    upload = run(editor_client, run_outbox, pdf_bytes())
    url, ttl = services.document_link(
        key=upload.base_key, filename="Term sheet.pdf", content_type=PDF
    )
    assert url.startswith("https://private.test/") and f"expires_in={ttl}" in url
    assert ttl == 300
