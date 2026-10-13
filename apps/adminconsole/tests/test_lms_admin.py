import pytest
from django.utils import timezone

from apps.learning import authoring
from apps.learning.models import Course, CourseRating, Enrolment, EnrolmentRequest
from apps.learning.tests.conftest import build_course
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
def course(editor):
    return build_course(editor)


@pytest.fixture
def paid(editor):
    return build_course(editor, access="paid", price_minor=50000, currency="NGN")


def call(client, method, path, payload=None):
    send = getattr(client, method)
    return send(path, payload, format="json") if payload is not None else send(path)


# --- who may call what ---

ENDPOINTS = [
    ("get", f"{ADMIN}/course-requests", None),
    ("get", f"{ADMIN}/courses/{NIL}/requests", None),
    ("post", f"{ADMIN}/course-requests/{NIL}/approve", None),
    ("post", f"{ADMIN}/course-requests/{NIL}/decline", None),
    ("get", f"{ADMIN}/courses/{NIL}/learners", None),
    ("get", f"{ADMIN}/courses/{NIL}/learners.csv", None),
    ("delete", f"{ADMIN}/courses/{NIL}/learners/{NIL}", None),
    ("get", f"{ADMIN}/courses/{NIL}/reviews", None),
    ("get", f"{ADMIN}/courses/{NIL}/questions", None),
    ("get", f"{ADMIN}/courses/{NIL}/announcements", None),
    ("post", f"{ADMIN}/courses/{NIL}/announcements", {"title": "Hi", "body": "<p>x</p>"}),
    ("post", f"{ADMIN}/questions/{NIL}/answer", {"body": "x"}),
    ("post", f"{ADMIN}/youtube/validate", {"url": "https://youtu.be/dQw4w9WgXcQ"}),
    ("post", f"{ADMIN}/modules/{NIL}/lessons/bulk", {"urls": ["https://youtu.be/dQw4w9WgXcQ"]}),
    ("post", f"{ADMIN}/reviews/{NIL}/hide", None),
    ("post", f"{ADMIN}/reviews/{NIL}/restore", None),
    ("post", f"{ADMIN}/questions/{NIL}/hide", None),
    ("post", f"{ADMIN}/questions/{NIL}/restore", None),
    ("post", f"{ADMIN}/answers/{NIL}/hide", None),
    ("post", f"{ADMIN}/answers/{NIL}/restore", None),
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


@pytest.mark.parametrize("method,path,payload", ENDPOINTS[1:])
def test_an_unknown_item_is_not_found(as_editor, method, path, payload):
    if "youtube" in path:
        pytest.skip("takes no id")
    assert call(as_editor, method, path, payload).status_code == 404


# --- access requests ---


def asked(client, paid_course, message="For my team"):
    response = client.post(
        f"/api/v1/courses/{paid_course.pk}/request-access", {"message": message}, format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()["id"]


def test_requests_are_listed_across_courses_and_per_course_with_who_asked(
    as_editor, paid, learner_client, learner
):
    asked(learner_client, paid)
    page = as_editor.get(f"{ADMIN}/course-requests", {"status": "pending"}).json()
    [row] = page["results"]
    assert row["user"] == {"id": str(learner.pk), "name": "learner", "email": "learner@example.com"}
    assert row["course"]["title"] == paid.title and row["message"] == "For my team"
    assert as_editor.get(f"{ADMIN}/courses/{paid.pk}/requests").json()["count"] == 1
    assert as_editor.get(f"{ADMIN}/course-requests", {"status": "approved"}).json()["count"] == 0
    assert as_editor.get(f"{ADMIN}/course-requests", {"status": "maybe"}).status_code == 400


def test_approving_gives_the_course_and_tells_the_member(
    as_editor, paid, learner_client, learner, run_outbox
):
    request_id = asked(learner_client, paid)
    done = as_editor.post(f"{ADMIN}/course-requests/{request_id}/approve")
    assert done.status_code == 200 and done.json()["status"] == "approved"
    assert Enrolment.objects.filter(course=paid, user=learner, source="grant").exists()
    run_outbox()
    assert Notification.objects.filter(user=learner, type="course_granted").count() == 1
    assert Course.objects.get(pk=paid.pk).learners_count == 1
    assert as_editor.post(f"{ADMIN}/course-requests/{request_id}/approve").status_code == 409


def test_declining_tells_the_member_and_they_may_ask_again(
    as_editor, paid, learner_client, learner
):
    request_id = asked(learner_client, paid)
    assert (
        as_editor.post(f"{ADMIN}/course-requests/{request_id}/decline").json()["status"]
        == "rejected"
    )
    assert Notification.objects.filter(user=learner, type="course_request_declined").count() == 1
    assert not Enrolment.objects.filter(course=paid, user=learner).exists()
    assert as_editor.post(f"{ADMIN}/course-requests/{request_id}/decline").status_code == 409
    assert asked(learner_client, paid) != request_id
    assert EnrolmentRequest.objects.filter(course=paid, status="pending").count() == 1


def test_a_removed_member_cannot_be_given_a_course(as_editor, paid, learner_client, learner):
    request_id = asked(learner_client, paid)
    learner.status = "suspended"
    learner.save(update_fields=["status"])
    assert as_editor.post(f"{ADMIN}/course-requests/{request_id}/approve").status_code == 400


# --- learners ---


def test_learners_show_name_email_and_progress_and_can_be_removed(
    as_editor, course, learner_client, learner
):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    first = course.lessons.order_by("module__position", "position").first()
    learner_client.put(f"/api/v1/lessons/{first.pk}/progress", {"completed": True}, format="json")
    page = as_editor.get(f"{ADMIN}/courses/{course.pk}/learners").json()
    assert page["count"] == 1
    assert (page["results"][0]["email"], page["results"][0]["percent"]) == (
        "learner@example.com",
        33,
    )
    assert as_editor.delete(f"{ADMIN}/courses/{course.pk}/learners/{learner.pk}").status_code == 204
    assert Course.objects.get(pk=course.pk).learners_count == 0
    assert as_editor.delete(f"{ADMIN}/courses/{course.pk}/learners/{learner.pk}").status_code == 404


def test_the_csv_lists_everyone_and_neutralises_formulae(
    as_editor, editor, course, learner_client, learner
):
    from apps.profiles.models import FounderProfile
    from apps.profiles.services import get_or_create_profile

    profile = get_or_create_profile(learner.pk)
    FounderProfile.objects.filter(pk=profile.pk).update(full_name="=HYPERLINK(1)")
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    response = as_editor.get(f"{ADMIN}/courses/{course.pk}/learners.csv")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert "attachment" in response["Content-Disposition"]
    body = response.content.decode()
    assert body.splitlines()[0] == "Name,Email,How they joined,Started,Progress %,Completed"
    assert "'=HYPERLINK(1)" in body and "learner@example.com" in body


# --- reviews, questions, answers ---


def test_reviews_can_be_hidden_and_restored_and_the_average_follows(
    as_editor, course, learner_client
):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    first = course.lessons.order_by("module__position", "position").first()
    learner_client.put(f"/api/v1/lessons/{first.pk}/progress", {"completed": True}, format="json")
    learner_client.put(
        f"/api/v1/courses/{course.pk}/rating", {"stars": 2, "feedback": "Meh"}, format="json"
    )
    [review] = as_editor.get(f"{ADMIN}/courses/{course.pk}/reviews").json()
    assert review["hidden"] is False and review["stars"] == 2
    assert as_editor.post(f"{ADMIN}/reviews/{review['id']}/hide").status_code == 204
    assert as_editor.get(f"{ADMIN}/courses/{course.pk}/reviews").json()[0]["hidden"] is True
    assert Course.objects.get(pk=course.pk).rating_count == 0
    assert as_editor.post(f"{ADMIN}/reviews/{review['id']}/restore").status_code == 204
    assert (
        Course.objects.get(pk=course.pk).rating_count == 1
        and CourseRating.objects.get().hidden_at is None
    )


def test_staff_answer_a_question_and_hide_questions_and_answers(
    as_editor, course, learner_client, learner
):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    lecture = course.lessons.order_by("module__position", "position").first()
    qid = learner_client.post(
        f"/api/v1/lessons/{lecture.pk}/questions", {"body": "What is vesting?"}, format="json"
    ).json()["id"]
    answered = as_editor.post(
        f"{ADMIN}/questions/{qid}/answer", {"body": "Earning shares over time."}, format="json"
    )
    assert answered.status_code == 201
    [question] = as_editor.get(f"{ADMIN}/courses/{course.pk}/questions").json()
    assert question["lecture"] == lecture.title and question["asker"] == "learner"
    [answer] = question["answers"]
    assert answer["is_staff"] is True
    assert as_editor.post(f"{ADMIN}/answers/{answer['id']}/hide").status_code == 204
    assert (
        as_editor.get(f"{ADMIN}/courses/{course.pk}/questions").json()[0]["answers"][0]["hidden"]
        is True
    )
    assert learner_client.get(f"/api/v1/lessons/{lecture.pk}/questions").json()[0]["answers"] == []
    assert as_editor.post(f"{ADMIN}/questions/{qid}/hide").status_code == 204
    assert learner_client.get(f"/api/v1/lessons/{lecture.pk}/questions").json() == []
    assert as_editor.post(f"{ADMIN}/questions/{qid}/restore").status_code == 204
    assert len(learner_client.get(f"/api/v1/lessons/{lecture.pk}/questions").json()) == 1


def test_an_answer_needs_text(as_editor, course, learner_client):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    lecture = course.lessons.order_by("module__position", "position").first()
    qid = learner_client.post(
        f"/api/v1/lessons/{lecture.pk}/questions", {"body": "Why?"}, format="json"
    ).json()["id"]
    assert (
        as_editor.post(f"{ADMIN}/questions/{qid}/answer", {"body": ""}, format="json").status_code
        == 400
    )


# --- announcements ---


def test_an_announcement_reaches_enrolled_learners(as_editor, course, learner_client, learner):
    learner_client.post(f"/api/v1/courses/{course.pk}/enrol")
    posted = as_editor.post(
        f"{ADMIN}/courses/{course.pk}/announcements",
        {"title": "Week two is live", "body": "<p>Go watch it.</p><script>x</script>"},
        format="json",
    )
    assert posted.status_code == 201 and "<script" not in posted.json()["body"]
    assert (
        as_editor.get(f"{ADMIN}/courses/{course.pk}/announcements").json()[0]["title"]
        == "Week two is live"
    )
    assert Notification.objects.filter(user=learner, type="course_announcement").count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "", "body": "<p>x</p>"},
        {"title": "T", "body": ""},
        {"title": "T", "body": "<p> </p>"},
        {"title": "x" * 161, "body": "<p>x</p>"},
    ],
)
def test_a_bad_announcement_is_refused(as_editor, course, payload):
    assert (
        as_editor.post(
            f"{ADMIN}/courses/{course.pk}/announcements", payload, format="json"
        ).status_code
        == 400
    )


# --- YouTube links ---


def test_a_youtube_link_is_checked_and_described(as_editor):
    body = as_editor.post(
        f"{ADMIN}/youtube/validate", {"url": "https://youtu.be/dQw4w9WgXcQ"}, format="json"
    ).json()
    assert body["video_id"] == "dQw4w9WgXcQ" and body["url"].endswith("v=dQw4w9WgXcQ")
    assert body["title"] == "Video dQw4w9WgXcQ" and body["thumbnail"].endswith(
        "/dQw4w9WgXcQ/mqdefault.jpg"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x",
        "http://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/playlist?list=x",
        "nonsense",
    ],
)
def test_anything_but_a_video_link_is_refused(as_editor, url):
    assert (
        as_editor.post(f"{ADMIN}/youtube/validate", {"url": url}, format="json").status_code == 400
    )


def test_pasting_links_adds_lectures_through_the_api(as_editor, editor):
    draft = authoring.create_course(actor=editor, data={"title": "Bulk"})
    module = authoring.add_module(actor=editor, course_id=draft.pk, title="Basics")
    done = as_editor.post(
        f"{ADMIN}/modules/{module.pk}/lessons/bulk",
        {"urls": ["https://youtu.be/dQw4w9WgXcQ", "https://youtu.be/9bZkp7q19f0"]},
        format="json",
    )
    assert done.status_code == 201 and [x["title"] for x in done.json()] == [
        "Video dQw4w9WgXcQ",
        "Video 9bZkp7q19f0",
    ]
    bad = as_editor.post(
        f"{ADMIN}/modules/{module.pk}/lessons/bulk",
        {"urls": ["https://youtu.be/9bZkp7q19f0", "bad"]},
        format="json",
    )
    assert bad.status_code == 400 and module.lessons.count() == 2
    assert (
        as_editor.post(
            f"{ADMIN}/modules/{module.pk}/lessons/bulk", {"urls": []}, format="json"
        ).status_code
        == 400
    )
    assert (
        as_editor.post(
            f"{ADMIN}/modules/{module.pk}/lessons/bulk",
            {"urls": ["https://youtu.be/9bZkp7q19f0"] * 31},
            format="json",
        ).status_code
        == 400
    )


# --- publishing as unlisted, the checklist, a draft with a title only ---


def test_a_course_can_be_published_unlisted_and_the_checklist_is_on_it(
    as_editor, editor, learner_client
):
    live = build_course(editor, publish=False)
    Course.objects.filter(pk=live.pk).update(cover_key="media/course_cover/test")
    detail = as_editor.get(f"{ADMIN}/courses/{live.pk}").json()
    assert all(item["done"] for item in detail["checklist"]) and detail["pending_requests"] == 0
    done = as_editor.post(f"{ADMIN}/courses/{live.pk}/publish", {"unlisted": True}, format="json")
    assert done.status_code == 200 and done.json()["status"] == "unlisted"
    assert (
        as_editor.post(
            f"{ADMIN}/courses/{live.pk}/publish", {"unlisted": True}, format="json"
        ).status_code
        == 409
    )
    assert as_editor.get(f"{ADMIN}/courses", {"status": "unlisted"}).json()["count"] == 1
    assert learner_client.get(f"/api/v1/courses/page/{live.slug}").status_code == 200
    assert as_editor.post(f"{ADMIN}/courses/{live.pk}/unpublish").json()["status"] == "draft"


def test_a_course_can_be_started_with_only_a_title_and_filled_in_later(as_editor):
    made = as_editor.post(f"{ADMIN}/courses", {"title": "Starting small"}, format="json")
    assert made.status_code == 201 and made.json()["level"] == "all"
    missing = {item["key"] for item in made.json()["checklist"] if not item["done"]}
    assert missing == {"description", "category", "curriculum"}
    patched = as_editor.get(f"{ADMIN}/courses/{made.json()['id']}")
    etag = patched["ETag"]
    done = as_editor.patch(
        f"{ADMIN}/courses/{made.json()['id']}",
        {
            "subtitle": "A short line",
            "learn_bullets": ["One", "Two"],
            "language": "fr",
            "audience": "Founders",
        },
        format="json",
        HTTP_IF_MATCH=etag,
    )
    assert done.status_code == 200
    body = done.json()
    assert (
        body["subtitle"] == "A short line"
        and body["learn_bullets"] == ["One", "Two"]
        and body["language"] == "fr"
    )
