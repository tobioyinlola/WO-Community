import uuid

import pytest

from apps.analytics.models import AnalyticsEvent
from apps.learning import authoring, learn
from apps.learning.models import Course, Enrolment, LessonProgress
from apps.learning.tests.conftest import build_course, lesson_ids

pytestmark = pytest.mark.django_db

COURSES = "/api/v1/courses"


def url(course, tail=""):
    return f"{COURSES}/{course.pk}{tail}"


def lesson_url(lesson_id, tail=""):
    return f"/api/v1/lessons/{lesson_id}{tail}"


def enrol(client, course):
    return client.post(url(course, "/enrol"))


def progress(client, lesson_id, **body):
    return client.put(lesson_url(lesson_id, "/progress"), body, format="json")


# --- the catalogue ---


def test_members_see_published_courses_with_their_details(course, learner_client):
    page = learner_client.get(COURSES).json()
    [item] = page["results"]
    assert item["title"] == "Fundraising basics" and item["lesson_count"] == 3
    assert item["access"] == "free" and item["price"] is None
    assert item["progress"]["enrolled"] is False and item["progress"]["percent"] == 0
    assert item["rating"] == {"average": None, "count": 0}


def test_drafts_are_not_in_the_catalogue(editor, learner_client):
    build_course(editor, publish=False, title="Draft course")
    assert learner_client.get(COURSES).json()["results"] == []


def test_the_catalogue_filters_and_pages(editor, learner_client):
    build_course(editor, title="Alpha", category="finance", level="beginner")
    build_course(editor, title="Beta", category="product", level="advanced")
    build_course(
        editor,
        title="Gamma",
        category="finance",
        level="advanced",
        access="paid",
        price_minor=500000,
        currency="NGN",
    )

    def titles(**params):
        return sorted(c["title"] for c in learner_client.get(COURSES, params).json()["results"])

    assert titles(category="finance") == ["Alpha", "Gamma"]
    assert titles(level="advanced") == ["Beta", "Gamma"]
    assert titles(access="paid") == ["Gamma"]
    assert titles(q="beta") == ["Beta"]
    page = learner_client.get(COURSES, {"limit": 2}).json()
    assert len(page["results"]) == 2 and page["next_cursor"]
    assert (
        len(
            learner_client.get(COURSES, {"limit": 2, "cursor": page["next_cursor"]}).json()[
                "results"
            ]
        )
        == 1
    )
    assert learner_client.get(f"{COURSES}/categories").json() == {
        "categories": ["finance", "product"]
    }


def test_a_paid_course_shows_its_price_in_minor_units(editor, learner_client):
    build_course(editor, access="paid", price_minor=1250000, currency="ngn")
    [item] = learner_client.get(COURSES).json()["results"]
    assert item["price"] == {"amount_minor": 1250000, "currency": "NGN"}


@pytest.mark.parametrize(
    "params",
    [
        {"level": "expert"},
        {"access": "gift"},
        {"limit": 0},
        {"limit": 51},
        {"cursor": "x"},
        {"z": 1},
    ],
)
def test_bad_catalogue_queries_are_refused(learner_client, params):
    assert learner_client.get(COURSES, params).status_code == 400


def test_the_learning_hub_is_for_active_members(api_client, make_user, client_for, course):
    assert api_client.get(COURSES).status_code == 401
    pending = client_for(make_user(email="p@example.com", status="pending"))
    assert pending.get(COURSES).status_code == 403
    assert pending.post(url(course, "/enrol")).status_code == 403


# --- enrolling ---


def test_enrolling_is_one_action_and_idempotent(course, learner_client, learner):
    first = enrol(learner_client, course)
    assert first.status_code == 201 and first.json()["origin"] == "free" and first.json()["created"]
    again = enrol(learner_client, course)
    assert again.status_code == 200 and again.json()["created"] is False
    assert Enrolment.objects.count() == 1
    [event] = AnalyticsEvent.objects.filter(name="course_enrolled")
    assert event.actor_id == learner.pk
    assert event.properties == {"course_id": course.slug, "access": "free"}


def test_paid_courses_cannot_be_enrolled_in_without_a_purchase(editor, learner_client):
    paid = build_course(editor, access="paid", price_minor=500000, currency="NGN")
    response = enrol(learner_client, paid)
    assert response.status_code == 402 and response.json()["code"] == "payment_required"
    assert Enrolment.objects.count() == 0


def test_you_cannot_enrol_in_drafts_or_unknown_courses(editor, learner_client):
    draft = build_course(editor, publish=False)
    assert enrol(learner_client, draft).status_code == 404
    assert learner_client.post(f"{COURSES}/{uuid.uuid4()}/enrol").status_code == 404


def test_my_courses_lists_enrolments_with_progress(editor, course, learner_client):
    other_course = build_course(editor, title="Other")
    enrol(learner_client, course)
    mine = learner_client.get("/api/v1/me/courses").json()["results"]
    assert [c["title"] for c in mine] == ["Fundraising basics"]
    assert mine[0]["progress"]["enrolled"] is True and other_course.pk
    assert [
        c["title"] for c in learner_client.get(COURSES, {"enrolled": "true"}).json()["results"]
    ] == ["Fundraising basics"]


# --- outline and lessons ---


def test_the_outline_locks_lessons_until_enrolment(course, learner_client):
    detail = learner_client.get(url(course)).json()
    assert [m["title"] for m in detail["modules"]] == ["Getting started", "Going deeper"]
    lessons = [x for m in detail["modules"] for x in m["lessons"]]
    assert [x["type"] for x in lessons] == ["video", "reading", "resource"]
    assert all(x["locked"] for x in lessons) and detail["resume"] is None
    enrol(learner_client, course)
    unlocked = learner_client.get(url(course)).json()
    assert not any(x["locked"] for m in unlocked["modules"] for x in m["lessons"])
    assert unlocked["resume"] == {"lesson_id": str(lesson_ids(course)[0]), "position_seconds": 0}


def test_lessons_need_enrolment(course, learner_client):
    video = lesson_ids(course)[0]
    response = learner_client.get(lesson_url(video))
    assert response.status_code == 403 and response.json()["code"] == "entitlement_required"
    enrol(learner_client, course)
    assert learner_client.get(lesson_url(video)).status_code == 200


def test_each_lesson_type_gives_what_it_should(course, learner_client):
    enrol(learner_client, course)
    video, reading, resource = (
        learner_client.get(lesson_url(i)).json() for i in lesson_ids(course)
    )
    assert video["video"] == {
        "provider": "youtube",
        "video_id": "dQw4w9WgXcQ",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "embed_url": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    }
    assert video["body"] == "" and video["resource"] is None and video["duration_seconds"] == 300
    assert "<strong>terms</strong>" in reading["body"] and reading["video"] is None
    assert resource["resource"] == {
        "url": "https://files.example.com/term-sheet.pdf",
        "name": "Term sheet template",
    }
    assert (video["previous_lesson_id"], video["next_lesson_id"]) == (None, reading["id"])
    assert (resource["previous_lesson_id"], resource["next_lesson_id"]) == (reading["id"], None)
    assert video["course"]["slug"] == course.slug and video["module"]["title"] == "Getting started"


def test_unknown_lessons_are_404(learner_client):
    assert learner_client.get(lesson_url(uuid.uuid4())).status_code == 404


# --- paid courses: the video id stays hidden without access ---


def test_a_paid_courses_video_id_never_reaches_someone_without_access(
    editor, learner_client, learner
):
    paid = build_course(editor, access="paid", price_minor=500000, currency="NGN")
    video = lesson_ids(paid)[0]
    response = learner_client.get(lesson_url(video))
    assert response.status_code == 403 and "dQw4w9WgXcQ" not in response.content.decode()
    outline = learner_client.get(url(paid)).content.decode()
    assert "dQw4w9WgXcQ" not in outline and "youtube" not in outline
    learn.grant(actor=editor, course_id=paid.pk, user_id=learner.pk)
    assert learner_client.get(lesson_url(video)).json()["video"]["video_id"] == "dQw4w9WgXcQ"


# --- visitors ---


def test_a_free_course_open_to_visitors_can_be_watched_without_logging_in(editor, api_client):
    open_course = build_course(editor, open_to_visitors=True)
    video = lesson_ids(open_course)[0]
    response = api_client.get(lesson_url(video))
    assert response.status_code == 200 and response.json()["video"]["video_id"] == "dQw4w9WgXcQ"
    assert response.json()["progress"] is None
    closed = build_course(editor, title="Members only")
    assert api_client.get(lesson_url(lesson_ids(closed)[0])).status_code == 401


def test_visitors_are_throttled_harder_than_members(
    editor, api_client, learner_client, monkeypatch
):
    from apps.learning.views import AnonymousLessonThrottle

    monkeypatch.setattr(AnonymousLessonThrottle, "THROTTLE_RATES", {"lesson_visitor": "2/min"})
    open_course = build_course(editor, open_to_visitors=True)
    video = lesson_ids(open_course)[0]
    assert [api_client.get(lesson_url(video)).status_code for _ in range(3)] == [200, 200, 429]
    assert learner_client.get(lesson_url(video)).status_code == 200  # members are not held to it


def test_the_public_catalogue_lists_only_free_courses_open_to_visitors(editor, api_client):
    shown = build_course(editor, title="Open one", open_to_visitors=True)
    build_course(editor, title="Members only")
    build_course(editor, title="Paid", access="paid", price_minor=100, currency="USD")
    page = api_client.get("/api/v1/public/courses").json()
    assert [c["slug"] for c in page["results"]] == [shown.slug]
    detail = api_client.get(f"/api/v1/public/courses/{shown.slug}").json()
    assert [m["title"] for m in detail["modules"]] == ["Getting started", "Going deeper"]
    assert "video_id" not in str(detail) and "dQw4w9WgXcQ" not in str(detail)
    assert api_client.get("/api/v1/public/courses/members-only-zzz").status_code == 404


def test_courses_cannot_be_both_paid_and_open_to_visitors(editor):
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        build_course(editor, access="paid", price_minor=100, currency="USD", open_to_visitors=True)


# --- progress ---


def test_progress_saves_position_and_resumes(course, learner_client):
    enrol(learner_client, course)
    video = lesson_ids(course)[0]
    saved = progress(learner_client, video, position_seconds=125)
    assert saved.status_code == 200 and saved.json()["position_seconds"] == 125
    assert saved.json()["completed"] is False and saved.json()["course_percent"] == 0
    assert learner_client.get(lesson_url(video)).json()["progress"] == {
        "position_seconds": 125,
        "completed": False,
    }
    assert learner_client.get(url(course)).json()["resume"] == {
        "lesson_id": str(video),
        "position_seconds": 125,
    }
    progress(learner_client, video, position_seconds=200)
    assert LessonProgress.objects.get().position_seconds == 200  # the latest wins


def test_finishing_lessons_moves_the_percentage_and_the_resume_point(course, learner_client):
    enrol(learner_client, course)
    first, second, third = lesson_ids(course)
    assert progress(learner_client, first, completed=True).json()["course_percent"] == 33
    done = progress(learner_client, second, completed=True).json()
    assert done["course_percent"] == 66 and done["course_completed"] is False
    detail = learner_client.get(url(course)).json()
    assert detail["resume"] == {"lesson_id": str(third), "position_seconds": 0}
    assert [x["completed"] for m in detail["modules"] for x in m["lessons"]] == [True, True, False]
    assert detail["progress"]["completed_lessons"] == 2


def test_completing_the_last_lesson_completes_the_course_once(course, learner_client, learner):
    enrol(learner_client, course)
    for lesson in lesson_ids(course):
        last = progress(learner_client, lesson, completed=True).json()
    assert last["course_percent"] == 100 and last["course_completed"] is True
    progress(learner_client, lesson_ids(course)[0], completed=True)  # a repeat changes nothing
    names = list(AnalyticsEvent.objects.filter(actor_id=learner.pk).values_list("name", flat=True))
    assert names.count("course_completed") == 1 and names.count("lesson_completed") == 3
    assert names.count("lesson_started") == 3
    assert learner_client.get(url(course)).json()["resume"] is None


def test_a_lesson_can_be_marked_not_done(course, learner_client):
    enrol(learner_client, course)
    first = lesson_ids(course)[0]
    progress(learner_client, first, completed=True)
    assert progress(learner_client, first, completed=False).json()["completed"] is False
    assert progress(learner_client, first, completed=False).json()["course_percent"] == 0


@pytest.mark.parametrize(
    "body",
    [{}, {"position_seconds": -1}, {"position_seconds": 86401}, {"completed": "maybe"}, {"x": 1}],
)
def test_bad_progress_is_refused(course, learner_client, body):
    enrol(learner_client, course)
    assert progress(learner_client, lesson_ids(course)[0], **body).status_code == 400


def test_progress_needs_enrolment_and_belongs_to_the_member(course, learner_client, other_client):
    first = lesson_ids(course)[0]
    assert progress(learner_client, first, position_seconds=5).status_code == 403
    enrol(learner_client, course)
    progress(learner_client, first, position_seconds=50)
    assert progress(other_client, first, position_seconds=5).status_code == 403
    assert LessonProgress.objects.get().position_seconds == 50


def test_progress_needs_a_login(api_client, course):
    assert (
        api_client.put(
            lesson_url(lesson_ids(course)[0], "/progress"), {"completed": True}, format="json"
        ).status_code
        == 401
    )


def test_progress_is_rate_limited(course, learner_client, monkeypatch):
    from rest_framework.throttling import ScopedRateThrottle

    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "lesson_progress": "2/min"},
    )
    enrol(learner_client, course)
    first = lesson_ids(course)[0]
    codes = [progress(learner_client, first, position_seconds=i).status_code for i in range(3)]
    assert codes == [200, 200, 429]


# --- courses that change under learners ---


def test_unpublishing_hides_a_course_but_enrolled_members_keep_going(
    editor, course, learner_client, other_client
):
    enrol(learner_client, course)
    authoring.unpublish(actor=editor, course_id=course.pk)
    assert learner_client.get(COURSES).json()["results"] == []
    assert learner_client.get(url(course)).status_code == 200
    first = lesson_ids(course)[0]
    assert learner_client.get(lesson_url(first)).status_code == 200
    assert progress(learner_client, first, position_seconds=9).status_code == 200
    assert other_client.get(url(course)).status_code == 404
    assert enrol(other_client, course).status_code == 404


def test_removed_courses_vanish_for_everyone(editor, course, learner_client):
    enrol(learner_client, course)
    authoring.remove_course(actor=editor, course_id=course.pk)
    assert learner_client.get(url(course)).status_code == 404
    assert learner_client.get(lesson_url(lesson_ids(course)[0])).status_code == 404
    assert Course.objects.get(pk=course.pk).status == "removed"


def test_a_lesson_added_later_does_not_undo_a_completion(editor, course, learner_client):
    enrol(learner_client, course)
    for lesson in lesson_ids(course):
        progress(learner_client, lesson, completed=True)
    module = course.modules.first()
    authoring.add_lesson(
        actor=editor,
        module_id=module.pk,
        data={"type": "reading", "title": "Bonus", "body": "<p>More</p>"},
    )
    detail = learner_client.get(url(course)).json()
    assert detail["progress"]["completed_at"] is not None and detail["progress"]["percent"] == 75


# --- ratings ---


def test_enrolled_members_can_rate_and_change_their_rating(course, learner_client, other_client):
    assert (
        learner_client.put(url(course, "/rating"), {"stars": 5}, format="json").status_code == 403
    )
    enrol(learner_client, course)
    enrol(other_client, course)
    learner_client.put(
        url(course, "/rating"), {"stars": 5, "feedback": "Great <b>course</b>"}, format="json"
    )
    other_client.put(url(course, "/rating"), {"stars": 3}, format="json")
    detail = learner_client.get(url(course)).json()
    assert detail["rating"] == {"average": 4.0, "count": 2}
    assert detail["my_rating"] == {"stars": 5, "feedback": "Great course"}
    learner_client.put(url(course, "/rating"), {"stars": 1}, format="json")
    assert learner_client.get(url(course)).json()["rating"] == {"average": 2.0, "count": 2}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"stars": 0},
        {"stars": 6},
        {"stars": "x"},
        {"stars": 3, "feedback": "x" * 1001},
        {"stars": 3, "z": 1},
    ],
)
def test_bad_ratings_are_refused(course, learner_client, body):
    enrol(learner_client, course)
    assert learner_client.put(url(course, "/rating"), body, format="json").status_code == 400
