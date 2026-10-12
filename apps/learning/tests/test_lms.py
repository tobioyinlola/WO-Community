from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import exceptions

from apps.learning import authoring, lms
from apps.learning.models import Course, Lesson
from apps.learning.tests.conftest import VIDEO, build_course
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

COURSES = "/api/v1/courses"


def url(course, tail=""):
    return f"{COURSES}/{course.pk}{tail}"


def lesson_url(lesson_id, tail=""):
    return f"/api/v1/lessons/{lesson_id}{tail}"


def first_lesson(course):
    return course.lessons.order_by("module__position", "position").first()


def finish(client, lesson):
    return client.put(lesson_url(lesson.pk, "/progress"), {"completed": True}, format="json")


@pytest.fixture
def course(editor):
    return build_course(editor)


# --- catalogue: filters, sorts, the new facts ---


def test_the_summary_carries_what_the_catalogue_shows(editor, learner_client):
    course = build_course(editor, subtitle="Your first round", language="fr", level="all")
    Lesson.objects.filter(course=course).update(duration_seconds=1200)
    lms.refresh_counts(course.pk)
    [item] = learner_client.get(COURSES).json()["results"]
    assert item["subtitle"] == "Your first round" and item["language_label"] == "French"
    assert item["duration_seconds"] == 3600 and item["learners_count"] == 0
    assert item["wishlisted"] is False and item["access_request"] is None
    assert item["slug"] == course.slug and item["level"] == "all"


def test_filters_by_language_level_price_and_search(editor, learner_client):
    build_course(editor, title="Pricing for founders", category="finance")
    build_course(
        editor, title="Cuisine du Sénégal", language="fr", level="advanced", category="food"
    )
    build_course(editor, title="Paid masterclass", access="paid", price_minor=50000, currency="USD")

    def get(**q):
        rows = learner_client.get(COURSES, q).json()["results"]
        return [c["title"] for c in rows]

    assert get(language="fr") == ["Cuisine du Sénégal"]
    assert get(level="advanced") == ["Cuisine du Sénégal"]
    assert get(access="paid") == ["Paid masterclass"]
    assert get(q="pricing") == ["Pricing for founders"]
    assert get(q="masterclass") == ["Paid masterclass"]
    assert len(get()) == 3


def test_filters_by_duration_and_rating(editor, learner_client):
    short = build_course(editor, title="Short one")
    long_ = build_course(editor, title="Long one")
    Lesson.objects.filter(course=short).update(duration_seconds=600)
    Lesson.objects.filter(course=long_).update(duration_seconds=8000)
    lms.refresh_counts(short.pk)
    lms.refresh_counts(long_.pk)
    Course.objects.filter(pk=long_.pk).update(rating_count=2, rating_total=9)

    def get(**q):
        rows = learner_client.get(COURSES, q).json()["results"]
        return [c["title"] for c in rows]

    assert get(duration="short") == ["Short one"]
    assert get(duration="long") == ["Long one"]
    assert get(rating_min=4) == ["Long one"]
    assert get(rating_min=5) == []


def test_sorting_by_popularity_and_rating_pages_with_a_cursor(editor, learner_client):
    for n in range(3):
        c = build_course(editor, title=f"Course {n}")
        Course.objects.filter(pk=c.pk).update(
            learners_count=n * 10, rating_count=1, rating_total=n + 1
        )
    popular = learner_client.get(COURSES, {"sort": "popular", "limit": 2}).json()
    assert [c["title"] for c in popular["results"]] == ["Course 2", "Course 1"]
    rest = learner_client.get(
        COURSES, {"sort": "popular", "limit": 2, "cursor": popular["next_cursor"]}
    ).json()
    assert [c["title"] for c in rest["results"]] == ["Course 0"] and rest["next_cursor"] is None
    best = learner_client.get(COURSES, {"sort": "rating"}).json()["results"]
    assert [c["title"] for c in best][0] == "Course 2"


@pytest.mark.parametrize(
    "query", [{"sort": "random"}, {"duration": "forever"}, {"rating_min": 9}, {"level": "expert"}]
)
def test_bad_catalogue_queries_are_refused(learner_client, query):
    assert learner_client.get(COURSES, query).status_code == 400


# --- open for enrolment: unlisted, closed ---


def test_an_unlisted_course_is_reachable_by_link_and_open_for_enrolment_but_not_listed(
    editor, learner_client, other_client
):
    course = build_course(editor, publish=False)
    Course.objects.filter(pk=course.pk).update(cover_key="media/course_cover/test")
    authoring.publish(actor=editor, course_id=course.pk, unlisted=True)
    assert learner_client.get(COURSES).json()["results"] == []
    page = learner_client.get(f"{COURSES}/page/{course.slug}")
    assert page.status_code == 200 and page.json()["status"] == "unlisted"
    assert learner_client.post(url(course, "/enrol")).status_code == 201
    assert authoring.Course.objects.get(pk=course.pk).learners_count == 1


def test_a_draft_course_does_not_exist_for_other_members(editor, learner_client):
    course = build_course(editor, publish=False)
    assert learner_client.get(f"{COURSES}/page/{course.slug}").status_code == 404
    assert learner_client.get(f"{COURSES}/page/not-a-course").status_code == 404


def test_closed_enrolment_stops_new_learners_but_not_those_already_in(
    editor, learner_client, other_client
):
    course = build_course(editor)
    assert learner_client.post(url(course, "/enrol")).status_code == 201
    Course.objects.filter(pk=course.pk).update(enrolment_active=False)
    assert other_client.post(url(course, "/enrol")).status_code == 409
    assert learner_client.post(url(course, "/enrol")).status_code == 200


def test_the_counts_follow_enrolments_and_the_curriculum(editor, learner_client):
    course = build_course(editor)
    assert Course.objects.get(pk=course.pk).learners_count == 0
    learner_client.post(url(course, "/enrol"))
    Lesson.objects.filter(course=course).update(duration_seconds=100)
    lms.refresh_counts(course.pk)
    fresh = Course.objects.get(pk=course.pk)
    assert fresh.learners_count == 1 and fresh.total_duration_seconds == 300


# --- the course page, previews ---


def test_the_page_has_everything_that_explains_the_course(editor, learner_client):
    course = build_course(
        editor,
        learn_bullets=["Write a deck", "Price a round", ""],
        requirements=["A laptop"],
        audience="Founders who have not raised yet.",
        promo_video_url=VIDEO,
    )
    page = learner_client.get(f"{COURSES}/page/{course.slug}").json()
    assert page["learn_bullets"] == ["Write a deck", "Price a round"]
    assert page["requirements"] == ["A laptop"] and page["audience"].startswith("Founders")
    assert page["promo_video"]["video_id"] == "dQw4w9WgXcQ"
    assert page["rating_distribution"] == {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    assert page["section_count"] == 2 and page["can_review"] is False
    assert learner_client.get(f"{COURSES}/page/{course.pk}").json()["id"] == str(course.pk)


def test_related_courses_share_a_category_and_leave_out_this_one(editor, learner_client):
    one = build_course(editor, title="One", category="finance")
    build_course(editor, title="Two", category="finance")
    build_course(editor, title="Three", category="design")
    related = learner_client.get(f"{COURSES}/page/{one.slug}").json()["related"]
    assert [c["title"] for c in related] == ["Two"]


def test_a_preview_lecture_opens_for_anyone_signed_in_and_others_stay_locked(
    editor, learner_client, api_client
):
    course = build_course(editor)
    lecture, other = list(course.lessons.order_by("module__position", "position"))[:2]
    Lesson.objects.filter(pk=lecture.pk).update(is_preview=True)
    outline = learner_client.get(f"{COURSES}/page/{course.slug}").json()["modules"][0]["lessons"]
    assert [(x["preview"], x["locked"]) for x in outline[:2]] == [(True, False), (False, True)]
    opened = learner_client.get(lesson_url(lecture.pk))
    assert opened.status_code == 200 and opened.json()["preview"] is True
    assert learner_client.get(lesson_url(other.pk)).status_code == 403
    assert api_client.get(lesson_url(lecture.pk)).status_code in (401, 403)


# --- saving for later and the shelves ---


def test_saving_is_idempotent_and_shows_on_the_shelf(course, learner_client):
    assert learner_client.put(url(course, "/wishlist")).json() == {"saved": True}
    assert learner_client.put(url(course, "/wishlist")).status_code == 200
    assert learner_client.get(url(course)).json()["wishlisted"] is True
    shelf = learner_client.get("/api/v1/me/learning", {"state": "wishlist"}).json()["results"]
    assert [c["id"] for c in shelf] == [str(course.pk)]
    assert learner_client.delete(url(course, "/wishlist")).json() == {"saved": False}
    assert learner_client.get("/api/v1/me/learning", {"state": "wishlist"}).json()["results"] == []


def test_the_shelves_split_in_progress_and_completed(editor, learner_client):
    done = build_course(editor, title="Done")
    going = build_course(editor, title="Going")
    for c in (done, going):
        learner_client.post(url(c, "/enrol"))
    for lesson in done.lessons.all():
        finish(learner_client, lesson)

    def shelf(state):
        rows = learner_client.get("/api/v1/me/learning", {"state": state}).json()["results"]
        return [c["title"] for c in rows]

    assert shelf("completed") == ["Done"] and shelf("in_progress") == ["Going"]
    assert sorted(shelf("all")) == ["Done", "Going"]
    assert learner_client.get("/api/v1/me/learning", {"state": "other"}).status_code == 400


def test_progress_reports_the_time_left(editor, learner_client):
    course = build_course(editor)
    Lesson.objects.filter(course=course).update(duration_seconds=600)
    learner_client.post(url(course, "/enrol"))
    finish(learner_client, first_lesson(course))
    progress = learner_client.get(url(course)).json()["progress"]
    assert progress["percent"] == 33 and progress["time_remaining_seconds"] == 1200


# --- asking for a paid course ---


@pytest.fixture
def paid(editor):
    return build_course(editor, access="paid", price_minor=50000, currency="NGN")


def test_a_member_asks_for_a_paid_course_once_and_staff_are_told(paid, learner_client, editor):
    first = learner_client.post(
        url(paid, "/request-access"), {"message": "For my team"}, format="json"
    )
    assert first.status_code == 201 and first.json()["status"] == "pending"
    again = learner_client.post(url(paid, "/request-access"), {}, format="json")
    assert again.json()["id"] == first.json()["id"]
    assert Notification.objects.filter(user=editor, type="course_request").count() == 1
    assert learner_client.get(url(paid)).json()["access_request"] == "pending"


def test_only_paid_courses_take_requests_and_not_from_someone_already_in(
    course, paid, learner, learner_client
):
    from apps.learning.models import Enrolment

    assert learner_client.post(url(course, "/request-access"), {}, format="json").status_code == 409
    Enrolment.objects.create(course=paid, user=learner, source="grant", started_at=timezone.now())
    assert learner_client.post(url(paid, "/request-access"), {}, format="json").status_code == 409


def test_a_request_is_refused_while_enrolment_is_closed(paid, learner_client):
    Course.objects.filter(pk=paid.pk).update(enrolment_active=False)
    assert learner_client.post(url(paid, "/request-access"), {}, format="json").status_code == 409


def test_a_request_needs_a_signed_in_member(paid, api_client):
    assert api_client.post(url(paid, "/request-access"), {}, format="json").status_code == 401


# --- reviews ---


def test_a_review_waits_for_a_quarter_of_the_course_and_shows_in_the_list(
    course, learner_client, other_client
):
    learner_client.post(url(course, "/enrol"))
    early = learner_client.put(url(course, "/rating"), {"stars": 5}, format="json")
    assert early.status_code == 409 and "25 percent" in str(early.json())
    finish(learner_client, first_lesson(course))
    assert learner_client.get(f"{COURSES}/page/{course.slug}").json()["can_review"] is True
    done = learner_client.put(
        url(course, "/rating"), {"stars": 4, "feedback": "Clear <b>and</b> useful"}, format="json"
    )
    assert done.status_code in (200, 201)
    page = other_client.get(url(course, "/reviews")).json()
    assert page["count"] == 1 and page["average"] == 4.0
    assert page["distribution"] == {"5": 0, "4": 1, "3": 0, "2": 0, "1": 0}
    assert (
        page["results"][0]["feedback"] == "Clear and useful" and page["results"][0]["mine"] is False
    )
    assert learner_client.get(url(course, "/reviews")).json()["results"][0]["mine"] is True


def test_a_hidden_review_leaves_the_average_and_the_list(editor, course, learner_client):
    from apps.learning import engage
    from apps.learning.models import CourseRating

    learner_client.post(url(course, "/enrol"))
    finish(learner_client, first_lesson(course))
    learner_client.put(url(course, "/rating"), {"stars": 5}, format="json")
    review = CourseRating.objects.get()
    engage.set_hidden(actor=editor, kind="review", item_id=review.pk, hidden=True)
    assert Course.objects.get(pk=course.pk).rating_count == 0
    assert learner_client.get(url(course, "/reviews")).json()["results"] == []
    engage.set_hidden(actor=editor, kind="review", item_id=review.pk, hidden=False)
    assert Course.objects.get(pk=course.pk).rating_count == 1


# --- questions and answers, notes, announcements ---


def test_enrolled_learners_ask_and_answer_and_staff_answers_carry_a_badge(
    editor, course, learner_client, other_client
):
    from apps.learning import engage

    lecture = first_lesson(course)
    learner_client.post(url(course, "/enrol"))
    other_client.post(url(course, "/enrol"))
    asked = learner_client.post(
        lesson_url(lecture.pk, "/questions"), {"body": "What is a SAFE?"}, format="json"
    )
    assert asked.status_code == 201 and asked.json()["mine"] is True
    qid = asked.json()["id"]
    reply = other_client.post(
        f"/api/v1/questions/{qid}/answers", {"body": "A simple agreement."}, format="json"
    )
    assert reply.status_code == 201 and reply.json()["is_staff"] is False
    engage.answer(user=editor, question_id=qid, body="See lecture 3.")
    shown = learner_client.get(lesson_url(lecture.pk, "/questions")).json()
    assert [(a["is_staff"], a["body"]) for a in shown[0]["answers"]] == [
        (False, "A simple agreement."),
        (True, "See lecture 3."),
    ]
    assert Notification.objects.filter(type="lecture_answer").count() == 2


def test_questions_need_enrolment_and_text(course, learner_client, other_client):
    lecture = first_lesson(course)
    learner_client.post(url(course, "/enrol"))
    assert (
        other_client.post(
            lesson_url(lecture.pk, "/questions"), {"body": "Hi?"}, format="json"
        ).status_code
        == 403
    )
    assert other_client.get(lesson_url(lecture.pk, "/questions")).status_code == 403
    for bad in ({}, {"body": ""}, {"body": "<b></b>"}, {"body": "x" * 2001}):
        assert (
            learner_client.post(
                lesson_url(lecture.pk, "/questions"), bad, format="json"
            ).status_code
            == 400
        )


def test_hidden_questions_and_answers_disappear(editor, course, learner_client):
    from apps.learning import engage

    lecture = first_lesson(course)
    learner_client.post(url(course, "/enrol"))
    qid = learner_client.post(
        lesson_url(lecture.pk, "/questions"), {"body": "Spam?"}, format="json"
    ).json()["id"]
    engage.set_hidden(actor=editor, kind="question", item_id=qid, hidden=True)
    assert learner_client.get(lesson_url(lecture.pk, "/questions")).json() == []


def test_notes_are_private_ordered_and_deletable(course, learner_client, other_client):
    lecture = first_lesson(course)
    for client in (learner_client, other_client):
        client.post(url(course, "/enrol"))
    late = learner_client.post(
        lesson_url(lecture.pk, "/notes"), {"body": "Second", "seconds": 90}, format="json"
    )
    learner_client.post(
        lesson_url(lecture.pk, "/notes"), {"body": "First", "seconds": 10}, format="json"
    )
    assert [n["body"] for n in learner_client.get(lesson_url(lecture.pk, "/notes")).json()] == [
        "First",
        "Second",
    ]
    assert other_client.get(lesson_url(lecture.pk, "/notes")).json() == []
    assert other_client.delete(f"/api/v1/notes/{late.json()['id']}").status_code == 404
    assert learner_client.delete(f"/api/v1/notes/{late.json()['id']}").status_code == 204
    assert [n["body"] for n in learner_client.get(lesson_url(lecture.pk, "/notes")).json()] == [
        "First"
    ]


def test_notes_need_enrolment_and_are_bounded(course, learner_client, other_client):
    lecture = first_lesson(course)
    assert (
        other_client.post(
            lesson_url(lecture.pk, "/notes"), {"body": "x"}, format="json"
        ).status_code
        == 404
    )
    learner_client.post(url(course, "/enrol"))
    for bad in (
        {"body": ""},
        {"body": "x", "seconds": -1},
        {"body": "x", "seconds": 99999},
        {"body": "x", "extra": 1},
    ):
        assert (
            learner_client.post(lesson_url(lecture.pk, "/notes"), bad, format="json").status_code
            == 400
        )


def test_announcements_reach_learners_who_are_told_and_nobody_else(
    editor, course, learner_client, other_client
):
    from apps.learning import engage

    learner_client.post(url(course, "/enrol"))
    engage.announce(
        actor=editor,
        course_id=course.pk,
        title="New lecture",
        body="<p>Lecture 4 is up.</p><script>x</script>",
    )
    shown = learner_client.get(url(course, "/announcements")).json()
    assert shown[0]["title"] == "New lecture" and "<script" not in shown[0]["body"]
    assert Notification.objects.filter(type="course_announcement").count() == 1
    assert other_client.get(url(course, "/announcements")).status_code == 403
    assert learner_client.get(f"{COURSES}/page/{course.slug}").json()["announcement_count"] == 1


# --- authoring rules ---


def test_a_draft_starts_with_only_a_title(editor):
    course = authoring.create_course(actor=editor, data={"title": "Just a title"})
    assert course.level == "all" and course.status == "draft"
    assert [i["done"] for i in lms.publish_checklist(course)][:1] == [True]


def test_the_checklist_names_what_is_missing_and_publishing_refuses(editor):
    course = authoring.create_course(actor=editor, data={"title": "Thin"})
    todo = {i["key"] for i in lms.publish_checklist(course) if not i["done"]}
    assert todo == {"description", "category", "thumbnail", "curriculum"}
    with pytest.raises(exceptions.ValidationError) as caught:
        authoring.publish(actor=editor, course_id=course.pk)
    assert "Still to do" in str(caught.value)


def test_a_promotion_must_cost_less_and_end_after_it_starts(editor):
    now = timezone.now()
    base = {"title": "Promo", "access": "paid", "price_minor": 1000, "currency": "USD"}
    with pytest.raises(exceptions.ValidationError):
        authoring.create_course(actor=editor, data={**base, "promo_price_minor": 1000})
    with pytest.raises(exceptions.ValidationError):
        authoring.create_course(
            actor=editor,
            data={
                **base,
                "promo_price_minor": 500,
                "promo_starts_at": now,
                "promo_ends_at": now - timedelta(days=1),
            },
        )
    ok = authoring.create_course(
        actor=editor,
        data={
            **base,
            "promo_price_minor": 500,
            "promo_starts_at": now - timedelta(hours=1),
            "promo_ends_at": now + timedelta(days=1),
        },
    )
    assert lms.promo_active(ok) and lms.current_price_minor(ok) == 500


def test_a_promotion_shows_the_old_price_struck_out_only_while_it_runs(editor, learner_client):
    now = timezone.now()
    course = build_course(
        editor,
        access="paid",
        price_minor=1000,
        currency="USD",
        promo_price_minor=400,
        promo_ends_at=now + timedelta(days=2),
    )
    price = learner_client.get(f"{COURSES}/page/{course.slug}").json()["price"]
    assert (
        price["amount_minor"] == 400 and price["original_minor"] == 1000 and price["promo_ends_at"]
    )
    Course.objects.filter(pk=course.pk).update(promo_ends_at=now - timedelta(days=1))
    price = learner_client.get(f"{COURSES}/page/{course.slug}").json()["price"]
    assert price["amount_minor"] == 1000 and price["original_minor"] is None


def test_unsuitable_course_fields_are_refused(editor):
    for bad in (
        {"language": "xx"},
        {"learn_bullets": ["x"] * 9},
        {"promo_video_url": "https://example.com/video"},
        {"access": "paid", "price_minor": 100, "currency": "XYZ"},
    ):
        with pytest.raises(exceptions.ValidationError):
            authoring.create_course(actor=editor, data={"title": "Bad", **bad})


def test_pasted_links_become_lectures_titled_from_the_video(editor):
    course = authoring.create_course(actor=editor, data={"title": "Bulk"})
    module = authoring.add_module(actor=editor, course_id=course.pk, title="Basics")
    made = authoring.add_lessons_from_links(
        actor=editor,
        module_id=module.pk,
        urls=["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/9bZkp7q19f0", ""],
    )
    assert [m.title for m in made] == ["Video dQw4w9WgXcQ", "Video 9bZkp7q19f0"]
    assert [m.position for m in made] == [0, 1] and Course.objects.get(
        pk=course.pk
    ).learners_count == 0


def test_one_wrong_link_adds_none_and_is_named(editor):
    course = authoring.create_course(actor=editor, data={"title": "Bulk"})
    module = authoring.add_module(actor=editor, course_id=course.pk, title="Basics")
    with pytest.raises(exceptions.ValidationError) as caught:
        authoring.add_lessons_from_links(
            actor=editor,
            module_id=module.pk,
            urls=["https://youtu.be/9bZkp7q19f0", "https://example.com/x"],
        )
    assert "Link 2" in str(caught.value)
    assert module.lessons.count() == 0
