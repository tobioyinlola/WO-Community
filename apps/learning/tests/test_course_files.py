import pytest

from apps.integrations.storage.base import PRIVATE
from apps.integrations.storage.fake import FakeStorage
from apps.learning import authoring
from apps.learning.models import Lesson
from apps.learning.tests.conftest import build_course
from apps.uploads.models import Upload, UploadStatus
from apps.uploads.tests.test_documents import PDF, pdf_bytes

pytestmark = pytest.mark.django_db

UPLOADS = "/api/v1/uploads"


@pytest.fixture
def staff_client(editor, client_for):
    return client_for(editor, mfa_age=5)


def make_document(client, run_outbox, data=None, filename="Term sheet.pdf"):
    """Upload a document the way the admin console does, and return the ready upload."""
    from apps.integrations.storage.base import PresignedPost

    data = data or pdf_bytes()
    created = client.post(
        UPLOADS,
        {"purpose": "course_file", "content_type": PDF, "size": len(data), "filename": filename},
    )
    assert created.status_code == 201, created.content
    FakeStorage.client_upload(
        PresignedPost("https://storage.test/q", created.json()["form"]["form_data"], 900),
        data,
        PDF,
    )
    upload_id = created.json()["upload"]["id"]
    assert client.post(f"{UPLOADS}/{upload_id}/complete").status_code == 202
    run_outbox()
    upload = Upload.objects.get(pk=upload_id)
    assert upload.status == UploadStatus.READY, upload.reject_reason
    return upload


def resource_lesson(course):
    return course.lessons.get(type="resource")


def attach(editor, lesson, upload, **extra):
    return authoring.update_lesson(
        actor=editor, lesson_id=lesson.pk, data={"upload_id": upload.pk, **extra}
    )


# --- authoring ---


def test_a_resource_lesson_can_hold_an_uploaded_file(editor, staff_client, run_outbox):
    course = build_course(editor, publish=False)
    upload = make_document(staff_client, run_outbox)
    lesson = attach(editor, resource_lesson(course), upload)
    assert lesson.file_key == upload.base_key and lesson.resource_url == ""
    assert lesson.file_size == upload.size and lesson.file_content_type == PDF
    assert lesson.resource_name == "Term sheet template"  # the name already given is kept


def test_the_file_name_defaults_to_the_uploaded_name(editor, staff_client, run_outbox):
    course = build_course(editor, publish=False)
    upload = make_document(staff_client, run_outbox, filename="Cap table.pdf")
    lesson = authoring.update_lesson(
        actor=editor,
        lesson_id=resource_lesson(course).pk,
        data={"upload_id": upload.pk, "resource_name": ""},
    )
    assert lesson.resource_name == "Cap table.pdf"


def test_a_link_and_a_file_together_are_refused(editor, staff_client, run_outbox):
    course = build_course(editor, publish=False)
    upload = make_document(staff_client, run_outbox)
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        attach(editor, resource_lesson(course), upload, resource_url="https://example.com/x.pdf")


def test_an_upload_can_be_used_once_and_only_by_its_owner(
    editor, staff_client, run_outbox, make_user
):
    course = build_course(editor, publish=False)
    upload = make_document(staff_client, run_outbox)
    attach(editor, resource_lesson(course), upload)
    from rest_framework.exceptions import ValidationError

    other_course = build_course(editor, publish=False, title="Second course")
    with pytest.raises(ValidationError):
        attach(editor, resource_lesson(other_course), upload)  # already in use
    stranger = make_user(roles=("content_editor",), email="other-editor@example.com")
    fresh = make_document(staff_client, run_outbox)
    with pytest.raises(ValidationError):
        authoring.update_lesson(
            actor=stranger, lesson_id=resource_lesson(other_course).pk, data={"upload_id": fresh.pk}
        )


def test_an_image_upload_cannot_be_used_as_a_course_file(editor, staff_client, ready_upload):
    course = build_course(editor, publish=False)
    photo = ready_upload(editor, "post_image")
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        attach(editor, resource_lesson(course), photo)


def test_replacing_or_removing_the_file_deletes_the_stored_object(
    editor, staff_client, run_outbox, django_capture_on_commit_callbacks
):
    course = build_course(editor, publish=False)
    lesson = resource_lesson(course)
    first = make_document(staff_client, run_outbox)
    attach(editor, lesson, first)
    assert (PRIVATE, first.base_key) in FakeStorage.objects

    second = make_document(staff_client, run_outbox)
    with django_capture_on_commit_callbacks(execute=True):
        attach(editor, lesson, second)
    assert (PRIVATE, first.base_key) not in FakeStorage.objects
    assert (PRIVATE, second.base_key) in FakeStorage.objects

    # Giving a link instead lets go of the stored file.
    with django_capture_on_commit_callbacks(execute=True):
        authoring.update_lesson(
            actor=editor, lesson_id=lesson.pk, data={"resource_url": "https://example.com/a.pdf"}
        )
    lesson.refresh_from_db()
    assert lesson.file_key == "" and lesson.resource_url == "https://example.com/a.pdf"
    assert (PRIVATE, second.base_key) not in FakeStorage.objects


def test_deleting_a_lesson_deletes_its_file_unless_a_copy_still_uses_it(
    editor, staff_client, run_outbox, django_capture_on_commit_callbacks
):
    course = build_course(editor, publish=False)
    upload = make_document(staff_client, run_outbox)
    attach(editor, resource_lesson(course), upload)
    copy = authoring.duplicate(actor=editor, course_id=course.pk)
    copied = Lesson.objects.get(course=copy, type="resource")
    assert copied.file_key == upload.base_key  # shared, not copied

    with django_capture_on_commit_callbacks(execute=True):
        authoring.delete_lesson(actor=editor, lesson_id=resource_lesson(course).pk)
    assert (PRIVATE, upload.base_key) in FakeStorage.objects  # the copy still needs it
    with django_capture_on_commit_callbacks(execute=True):
        authoring.delete_lesson(actor=editor, lesson_id=copied.pk)
    assert (PRIVATE, upload.base_key) not in FakeStorage.objects


def test_changing_the_lesson_type_lets_go_of_the_file(
    editor, staff_client, run_outbox, django_capture_on_commit_callbacks
):
    course = build_course(editor, publish=False)
    upload = make_document(staff_client, run_outbox)
    lesson = attach(editor, resource_lesson(course), upload)
    with django_capture_on_commit_callbacks(execute=True):
        authoring.update_lesson(
            actor=editor, lesson_id=lesson.pk, data={"type": "reading", "body": "<p>Notes</p>"}
        )
    lesson.refresh_from_db()
    assert lesson.file_key == "" and lesson.file_size is None
    assert (PRIVATE, upload.base_key) not in FakeStorage.objects


def test_the_admin_api_attaches_a_file_and_shows_it(editor, staff_client, run_outbox):
    course = build_course(editor, publish=False)
    module = course.modules.get(position=1)
    upload = make_document(staff_client, run_outbox, filename="Checklist.pdf")
    created = staff_client.post(
        f"/api/v1/admin/modules/{module.pk}/lessons",
        {"type": "resource", "title": "Checklist", "upload_id": str(upload.pk)},
        format="json",
    )
    assert created.status_code == 201, created.content
    body = created.json()
    assert body["resource_url"] == "" and body["resource_name"] == "Checklist.pdf"
    assert body["file"] == {"name": "Checklist.pdf", "size": upload.size, "content_type": PDF}
    missing = staff_client.post(
        f"/api/v1/admin/modules/{module.pk}/lessons",
        {"type": "resource", "title": "Nothing"},
        format="json",
    )
    assert missing.status_code == 400


# --- members ---


@pytest.fixture
def with_file(editor, staff_client, run_outbox):
    course = build_course(editor)
    upload = make_document(staff_client, run_outbox)
    lesson = attach(editor, resource_lesson(course), upload)
    return course, lesson, upload


def test_an_enrolled_member_gets_a_short_lived_download_link(with_file, learner_client):
    course, lesson, upload = with_file
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    detail = learner_client.get(f"/api/v1/lessons/{lesson.pk}").json()["resource"]
    assert detail["kind"] == "file" and detail["url"] == ""  # never a public address
    assert detail["name"] == "Term sheet template" and detail["size"] == upload.size

    response = learner_client.get(f"/api/v1/lessons/{lesson.pk}/file")
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    body = response.json()
    assert body["url"].startswith("https://private.test/")
    assert "filename=Term%20sheet%20template.pdf" in body["url"]  # saved with the right extension
    assert body["expires_in"] == 300 and body["content_type"] == PDF


def test_the_link_needs_access_to_the_lesson(with_file, learner_client, api_client):
    course, lesson, _ = with_file
    assert (
        learner_client.get(f"/api/v1/lessons/{lesson.pk}/file").status_code == 403
    )  # not enrolled
    assert api_client.get(f"/api/v1/lessons/{lesson.pk}/file").status_code in (401, 404)


def test_visitors_get_the_file_only_on_a_course_opened_to_them(
    editor, staff_client, run_outbox, api_client
):
    course = build_course(editor, open_to_visitors=True)
    upload = make_document(staff_client, run_outbox)
    lesson = attach(editor, resource_lesson(course), upload)
    assert api_client.get(f"/api/v1/lessons/{lesson.pk}/file").status_code == 200


def test_a_lesson_without_a_stored_file_has_no_download(course, learner_client):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    lesson = resource_lesson(course)  # holds a link, not a file
    assert learner_client.get(f"/api/v1/lessons/{lesson.pk}/file").status_code == 404
    link = learner_client.get(f"/api/v1/lessons/{lesson.pk}").json()["resource"]
    assert link["kind"] == "link" and link["url"] == "https://files.example.com/term-sheet.pdf"
