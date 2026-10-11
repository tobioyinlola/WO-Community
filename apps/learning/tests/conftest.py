import pytest
from django.utils import timezone

from apps.learning import authoring

VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIDEO_TWO = "https://youtu.be/9bZkp7q19f0"


def active(make_user, email, **fields):
    return make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def learner(make_user):
    return active(make_user, "learner@example.com")


@pytest.fixture
def learner_client(learner, client_for):
    return client_for(learner)


@pytest.fixture
def other(make_user):
    return active(make_user, "other@example.com")


@pytest.fixture
def other_client(other, client_for):
    return client_for(other)


def build_course(editor, *, publish=True, **overrides):
    """A course with two modules and three lessons: video, reading, then a resource."""
    data = {
        "title": "Fundraising basics",
        "description": "<p>How to raise your first round.</p>",
        "instructor": "Ada Obi",
        "category": "finance",
        "level": "beginner",
    }
    data.update(overrides)
    course = authoring.create_course(actor=editor, data=data)
    first = authoring.add_module(actor=editor, course_id=course.pk, title="Getting started")
    second = authoring.add_module(actor=editor, course_id=course.pk, title="Going deeper")
    authoring.add_lesson(
        actor=editor,
        module_id=first.pk,
        data={"type": "video", "title": "Welcome", "video_url": VIDEO, "duration_seconds": 300},
    )
    authoring.add_lesson(
        actor=editor,
        module_id=first.pk,
        data={
            "type": "reading",
            "title": "Terms",
            "body": "<p>Read these <strong>terms</strong>.</p>",
        },
    )
    authoring.add_lesson(
        actor=editor,
        module_id=second.pk,
        data={
            "type": "resource",
            "title": "Template",
            "resource_url": "https://files.example.com/term-sheet.pdf",
            "resource_name": "Term sheet template",
        },
    )
    if publish:
        authoring.publish(actor=editor, course_id=course.pk)
    course.refresh_from_db()
    return course


def lesson_ids(course):
    return list(
        course.lessons.order_by("module__position", "position").values_list("pk", flat=True)
    )


@pytest.fixture
def course(editor):
    return build_course(editor)
