import uuid

import pytest
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.learning.models import Course, Enrolment, Lesson, Module
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db

ADMIN = "/api/v1/admin"
VIDEO = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def course_body(**overrides):
    body = {
        "title": "Pitching 101",
        "description": "<p>Tell your story.</p>",
        "instructor": "Ada Obi",
        "category": "storytelling",
        "level": "beginner",
    }
    body.update(overrides)
    return body


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


@pytest.fixture
def as_editor(editor, client_for):
    return client_for(editor, mfa_age=5)


@pytest.fixture
def member(make_user):
    return make_user(
        email="member@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )


@pytest.fixture
def member_client(member, client_for):
    return client_for(member)


def create(client, **overrides):
    response = client.post(f"{ADMIN}/courses", course_body(**overrides), format="json")
    assert response.status_code == 201, response.content
    return response.json()


def add_module(client, course, title="Module"):
    response = client.post(
        f"{ADMIN}/courses/{course['id']}/modules", {"title": title}, format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def add_lesson(client, module, **body):
    body = {"type": "video", "title": "Lesson", "video_url": VIDEO, **body}
    return client.post(f"{ADMIN}/modules/{module['id']}/lessons", body, format="json")


# --- courses ---


def test_an_editor_creates_a_draft_course(as_editor, editor):
    course = create(as_editor)
    assert course["status"] == "draft" and course["access"] == "free" and course["modules"] == []
    assert course["certificate_enabled"] is True and course["open_to_visitors"] is False
    assert AuditLog.objects.filter(action="courses.created").exists()
    assert Course.objects.get().created_by_id == editor.pk


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": ""},
        {"description": "<p></p>"},
        {"instructor": ""},
        {"category": ""},
        {"level": "expert"},
        {"access": "gift"},
        {"access": "paid"},  # needs a price
        {"access": "paid", "price_minor": 1000},  # and a currency
        {"access": "paid", "price_minor": 0, "currency": "NGN"},
        {"access": "paid", "price_minor": 1000, "currency": "NAIRA"},
        {"access": "paid", "price_minor": 1000, "currency": "N1"},
        {"access": "paid", "price_minor": 1000, "currency": "NGN", "open_to_visitors": True},
        {"status": "published"},
        {"slug": "x"},
    ],
)
def test_invalid_courses_are_refused(as_editor, overrides):
    assert (
        as_editor.post(f"{ADMIN}/courses", course_body(**overrides), format="json").status_code
        == 400
    )
    assert Course.objects.count() == 0


def test_a_paid_course_keeps_its_price_and_a_free_one_has_none(as_editor):
    paid = create(as_editor, access="paid", price_minor=2500000, currency="usd")
    assert (paid["price_minor"], paid["currency"]) == (2500000, "USD")
    assert paid["price"] == {"amount_minor": 2500000, "currency": "USD"}
    free = create(as_editor, title="Free one", price_minor=999, currency="NGN")
    assert free["price_minor"] is None and free["currency"] == ""


def test_editing_needs_the_etag_and_can_switch_access(as_editor):
    course = create(as_editor)
    url = f"{ADMIN}/courses/{course['id']}"
    etag = as_editor.get(url)["ETag"]
    changed = as_editor.patch(
        url,
        {"title": "Pitching 102", "access": "paid", "price_minor": 100000, "currency": "NGN"},
        format="json",
        HTTP_IF_MATCH=etag,
    )
    assert changed.status_code == 200 and changed.json()["title"] == "Pitching 102"
    assert changed.json()["access"] == "paid" and changed.json()["edited_at"]
    assert as_editor.patch(url, {"title": "x"}, format="json").status_code == 428
    assert (
        as_editor.patch(url, {"title": "x"}, format="json", HTTP_IF_MATCH=etag).status_code == 412
    )
    back = as_editor.patch(
        url, {"access": "free"}, format="json", HTTP_IF_MATCH=as_editor.get(url)["ETag"]
    )
    assert back.json()["price"] is None


def test_the_course_list_filters(as_editor):
    create(as_editor, title="Alpha")
    paid = create(as_editor, title="Beta", access="paid", price_minor=100, currency="USD")
    as_editor.post(f"{ADMIN}/courses/{paid['id']}/modules", {"title": "m"}, format="json")
    assert as_editor.get(f"{ADMIN}/courses").json()["count"] == 2
    assert as_editor.get(f"{ADMIN}/courses", {"access": "paid"}).json()["count"] == 1
    assert as_editor.get(f"{ADMIN}/courses", {"q": "alph"}).json()["count"] == 1
    assert as_editor.get(f"{ADMIN}/courses", {"status": "published"}).json()["count"] == 0
    assert as_editor.get(f"{ADMIN}/courses", {"status": "removed"}).status_code == 400


# --- modules and lessons ---


def test_modules_and_lessons_are_added_in_order(as_editor):
    course = create(as_editor)
    first, second = add_module(as_editor, course, "One"), add_module(as_editor, course, "Two")
    assert (first["position"], second["position"]) == (0, 1)
    a = add_lesson(as_editor, first, title="A").json()
    b = add_lesson(as_editor, first, title="B", video_url="https://youtu.be/9bZkp7q19f0").json()
    assert (a["position"], b["position"]) == (0, 1)
    assert (
        b["video_id"] == "9bZkp7q19f0"
        and b["video_url"] == "https://www.youtube.com/watch?v=9bZkp7q19f0"
    )
    detail = as_editor.get(f"{ADMIN}/courses/{course['id']}").json()
    assert [m["title"] for m in detail["modules"]] == ["One", "Two"]
    assert [x["title"] for x in detail["modules"][0]["lessons"]] == ["A", "B"]


@pytest.mark.parametrize(
    "body",
    [
        {"type": "video"},
        {"type": "video", "video_url": "https://vimeo.com/123456789"},
        {"type": "video", "video_url": "http://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        {"type": "video", "video_url": "https://evil.example.com/watch?v=dQw4w9WgXcQ"},
        {"type": "video", "video_url": "https://www.youtube.com/watch?v=short"},
        {"type": "video", "video_url": "https://www.youtube.com/playlist?list=PL1234567890A"},
        {"type": "reading"},
        {"type": "reading", "body": "<p></p>"},
        {"type": "resource"},
        {
            "type": "resource",
            "resource_url": "http://insecure.example.com/f.pdf",
            "resource_name": "x",
        },
        {"type": "resource", "resource_url": "https://files.example.com/f.pdf"},
        {"type": "resource", "resource_url": "javascript:alert(1)", "resource_name": "x"},
        {"type": "quiz", "title": "x"},
        {"type": "video", "video_url": VIDEO, "duration_seconds": 0},
        {"type": "video", "video_url": VIDEO, "x": 1},
    ],
)
def test_invalid_lessons_are_refused(as_editor, body):
    module = add_module(as_editor, create(as_editor))
    response = as_editor.post(
        f"{ADMIN}/modules/{module['id']}/lessons", {"title": "L", **body}, format="json"
    )
    assert response.status_code == 400
    assert Lesson.objects.count() == 0


def test_a_lesson_holds_only_what_its_type_needs(as_editor):
    module = add_module(as_editor, create(as_editor))
    lesson = add_lesson(as_editor, module).json()
    url = f"{ADMIN}/lessons/{lesson['id']}"
    reading = as_editor.patch(
        url, {"type": "reading", "body": "<p>Text <script>x()</script></p>"}, format="json"
    ).json()
    assert (
        reading["type"] == "reading"
        and reading["video_id"] == ""
        and "<script" not in reading["body"]
    )
    back = as_editor.patch(url, {"type": "video", "video_url": VIDEO}, format="json").json()
    assert back["video_id"] == "dQw4w9WgXcQ" and back["body"] == ""
    assert (
        as_editor.patch(
            url, {"type": "video", "video_url": "https://x.example.com"}, format="json"
        ).status_code
        == 400
    )


def test_reordering_needs_every_item_exactly_once(as_editor):
    course = create(as_editor)
    modules = [add_module(as_editor, course, t) for t in ("A", "B", "C")]
    ids = [m["id"] for m in modules]
    url = f"{ADMIN}/courses/{course['id']}/modules/order"
    done = as_editor.put(url, {"ids": [ids[2], ids[0], ids[1]]}, format="json")
    assert done.status_code == 200
    assert [m["title"] for m in done.json()["modules"]] == ["C", "A", "B"]
    for bad in ([ids[0]], [*ids, ids[0]], [ids[0], ids[1], str(uuid.uuid4())], []):
        assert as_editor.put(url, {"ids": bad}, format="json").status_code == 409
    assert [m.title for m in Module.objects.filter(course_id=course["id"])] == ["C", "A", "B"]


def test_lessons_reorder_within_a_module(as_editor):
    module = add_module(as_editor, create(as_editor))
    lessons = [add_lesson(as_editor, module, title=t).json() for t in ("x", "y", "z")]
    ids = [x["id"] for x in lessons]
    done = as_editor.put(
        f"{ADMIN}/modules/{module['id']}/lessons/order", {"ids": ids[::-1]}, format="json"
    )
    assert [x["title"] for x in done.json()["lessons"]] == ["z", "y", "x"]
    assert (
        as_editor.put(
            f"{ADMIN}/modules/{module['id']}/lessons/order", {"ids": ids[:2]}, format="json"
        ).status_code
        == 409
    )


def test_deleting_closes_the_gap_in_the_order(as_editor):
    course = create(as_editor)
    modules = [add_module(as_editor, course, t) for t in ("A", "B", "C")]
    assert as_editor.delete(f"{ADMIN}/modules/{modules[1]['id']}").status_code == 204
    assert [(m.title, m.position) for m in Module.objects.filter(course_id=course["id"])] == [
        ("A", 0),
        ("C", 1),
    ]
    lessons = [add_lesson(as_editor, modules[0], title=t).json() for t in ("x", "y", "z")]
    assert as_editor.delete(f"{ADMIN}/lessons/{lessons[0]['id']}").status_code == 204
    assert [(x.title, x.position) for x in Lesson.objects.filter(module_id=modules[0]["id"])] == [
        ("y", 0),
        ("z", 1),
    ]
    assert as_editor.delete(f"{ADMIN}/lessons/{lessons[0]['id']}").status_code == 404


def test_module_and_lesson_ids_from_other_courses_are_just_unknown(as_editor):
    assert (
        as_editor.patch(
            f"{ADMIN}/modules/{uuid.uuid4()}", {"title": "x"}, format="json"
        ).status_code
        == 404
    )
    assert (
        as_editor.post(
            f"{ADMIN}/modules/{uuid.uuid4()}/lessons",
            {"type": "reading", "title": "x", "body": "<p>x</p>"},
            format="json",
        ).status_code
        == 404
    )
    assert (
        as_editor.post(
            f"{ADMIN}/courses/{uuid.uuid4()}/modules", {"title": "x"}, format="json"
        ).status_code
        == 404
    )


# --- publishing, duplicating, removing ---


def test_publishing_needs_a_lesson_and_unpublishing_hides_the_course(as_editor, member_client):
    course = create(as_editor)
    base = f"{ADMIN}/courses/{course['id']}"
    assert as_editor.post(f"{base}/publish").status_code == 400
    add_lesson(as_editor, add_module(as_editor, course))
    live = as_editor.post(f"{base}/publish")
    assert live.status_code == 200 and live.json()["status"] == "published"
    assert as_editor.post(f"{base}/publish").status_code == 409
    assert member_client.get(f"/api/v1/courses/{course['id']}").status_code == 200
    assert as_editor.post(f"{base}/unpublish").json()["status"] == "draft"
    assert as_editor.post(f"{base}/unpublish").status_code == 409
    assert member_client.get(f"/api/v1/courses/{course['id']}").status_code == 404
    assert (
        AuditLog.objects.filter(action__in=["courses.published", "courses.unpublished"]).count()
        == 2
    )


def test_duplicating_makes_a_draft_copy_of_the_structure_only(as_editor, member_client):
    course = create(as_editor, access="paid", price_minor=100, currency="USD")
    module = add_module(as_editor, course, "Basics")
    add_lesson(as_editor, module, title="One")
    as_editor.post(f"{ADMIN}/courses/{course['id']}/publish")
    member_client.post(f"/api/v1/courses/{course['id']}/enrol")
    copy = as_editor.post(f"{ADMIN}/courses/{course['id']}/duplicate")
    assert copy.status_code == 201
    body = copy.json()
    assert (
        body["id"] != course["id"]
        and body["title"] == "Copy of Pitching 101"
        and body["status"] == "draft"
    )
    assert body["access"] == "paid" and body["price_minor"] == 100
    assert [m["title"] for m in body["modules"]] == ["Basics"]
    assert [x["title"] for x in body["modules"][0]["lessons"]] == ["One"]
    assert body["modules"][0]["id"] != module["id"]
    assert Enrolment.objects.filter(course_id=body["id"]).count() == 0
    assert Course.objects.get(pk=body["id"]).slug != Course.objects.get(pk=course["id"]).slug


def test_removing_a_course_hides_it_everywhere(as_editor):
    course = create(as_editor)
    assert as_editor.delete(f"{ADMIN}/courses/{course['id']}").status_code == 204
    assert as_editor.get(f"{ADMIN}/courses/{course['id']}").status_code == 404
    assert as_editor.delete(f"{ADMIN}/courses/{course['id']}").status_code == 404


def test_a_cover_is_set_and_cleared_from_a_finished_upload(as_editor, editor, ready_upload):
    course = create(as_editor)
    upload = ready_upload(editor, "course_cover")
    base = f"{ADMIN}/courses/{course['id']}/cover"
    done = as_editor.put(base, {"upload_id": str(upload.pk)}, format="json")
    assert done.status_code == 200 and done.json()["cover"]["large"].endswith("/large.webp")
    wrong = ready_upload(editor, "profile_photo")
    assert as_editor.put(base, {"upload_id": str(wrong.pk)}, format="json").status_code == 400
    assert as_editor.delete(base).json()["cover"] is None


# --- people and results ---


def published_with_lessons(client, lessons=2):
    course = create(client)
    module = add_module(client, course)
    for i in range(lessons):
        add_lesson(client, module, title=f"L{i}")
    client.post(f"{ADMIN}/courses/{course['id']}/publish")
    return course


def test_stats_enrolments_and_ratings(as_editor, member_client, member, make_user, client_for):
    course = published_with_lessons(as_editor)
    other = make_user(
        email="o@example.com", approved_at=timezone.now(), email_verified_at=timezone.now()
    )
    other_client = client_for(other)
    for client in (member_client, other_client):
        client.post(f"/api/v1/courses/{course['id']}/enrol")
    lessons = list(Lesson.objects.filter(course_id=course["id"]).order_by("position"))
    for lesson in lessons:
        member_client.put(
            f"/api/v1/lessons/{lesson.pk}/progress", {"completed": True}, format="json"
        )
    other_client.put(
        f"/api/v1/lessons/{lessons[0].pk}/progress", {"completed": True}, format="json"
    )
    member_client.put(
        f"/api/v1/courses/{course['id']}/rating", {"stars": 4, "feedback": "Useful"}, format="json"
    )
    stats = as_editor.get(f"{ADMIN}/courses/{course['id']}/stats").json()
    assert (stats["enrolled"], stats["completed"], stats["completion_rate"]) == (2, 1, 0.5)
    assert stats["rating"] == {"average": 4.0, "count": 1}
    assert [x["completed_by"] for x in stats["lessons"]] == [2, 1]
    people = as_editor.get(f"{ADMIN}/courses/{course['id']}/enrolments").json()
    by_user = {p["user_id"]: p for p in people["results"]}
    assert by_user[str(member.pk)]["percent"] == 100 and by_user[str(other.pk)]["percent"] == 50
    ratings = as_editor.get(f"{ADMIN}/courses/{course['id']}/ratings").json()
    assert ratings[0]["feedback"] == "Useful" and ratings[0]["user_id"] == str(member.pk)


def test_an_admin_can_give_a_member_access_to_a_paid_course(
    as_editor, member_client, member, run_outbox
):
    paid = create(as_editor, access="paid", price_minor=100000, currency="NGN")
    module = add_module(as_editor, paid)
    add_lesson(as_editor, module)
    as_editor.post(f"{ADMIN}/courses/{paid['id']}/publish")
    assert member_client.post(f"/api/v1/courses/{paid['id']}/enrol").status_code == 402
    granted = as_editor.post(
        f"{ADMIN}/courses/{paid['id']}/grant", {"user_id": str(member.pk)}, format="json"
    )
    assert (
        granted.status_code == 201
        and granted.json()["origin"] == "grant"
        and granted.json()["created"]
    )
    assert (
        as_editor.post(
            f"{ADMIN}/courses/{paid['id']}/grant", {"user_id": str(member.pk)}, format="json"
        ).status_code
        == 200
    )
    run_outbox()
    assert Notification.objects.filter(user=member, type="course_granted").count() == 1
    assert (
        member_client.get(f"/api/v1/courses/{paid['id']}").json()["progress"]["origin"] == "grant"
    )
    lesson = Lesson.objects.get(course_id=paid["id"])
    assert (
        member_client.get(f"/api/v1/lessons/{lesson.pk}").json()["video"]["video_id"]
        == "dQw4w9WgXcQ"
    )
    assert AuditLog.objects.filter(action="courses.granted").count() == 1


def test_access_can_only_be_granted_to_active_members(as_editor, make_user):
    course = published_with_lessons(as_editor)
    pending = make_user(email="p@example.com", status="pending")
    url = f"{ADMIN}/courses/{course['id']}/grant"
    assert as_editor.post(url, {"user_id": str(pending.pk)}, format="json").status_code == 400
    assert as_editor.post(url, {"user_id": str(uuid.uuid4())}, format="json").status_code == 400
    assert as_editor.post(url, {}, format="json").status_code == 400


# --- access control ---


ENDPOINTS = [
    ("get", f"{ADMIN}/courses"),
    ("post", f"{ADMIN}/courses"),
    ("get", f"{ADMIN}/courses/{uuid.uuid4()}"),
    ("patch", f"{ADMIN}/courses/{uuid.uuid4()}"),
    ("delete", f"{ADMIN}/courses/{uuid.uuid4()}"),
    ("post", f"{ADMIN}/courses/{uuid.uuid4()}/publish"),
    ("post", f"{ADMIN}/courses/{uuid.uuid4()}/unpublish"),
    ("post", f"{ADMIN}/courses/{uuid.uuid4()}/duplicate"),
    ("put", f"{ADMIN}/courses/{uuid.uuid4()}/cover"),
    ("post", f"{ADMIN}/courses/{uuid.uuid4()}/modules"),
    ("put", f"{ADMIN}/courses/{uuid.uuid4()}/modules/order"),
    ("patch", f"{ADMIN}/modules/{uuid.uuid4()}"),
    ("post", f"{ADMIN}/modules/{uuid.uuid4()}/lessons"),
    ("patch", f"{ADMIN}/lessons/{uuid.uuid4()}"),
    ("get", f"{ADMIN}/courses/{uuid.uuid4()}/stats"),
    ("get", f"{ADMIN}/courses/{uuid.uuid4()}/enrolments"),
    ("get", f"{ADMIN}/courses/{uuid.uuid4()}/ratings"),
    ("post", f"{ADMIN}/courses/{uuid.uuid4()}/grant"),
]


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_members_and_visitors_cannot_author_courses(api_client, member_client, method, url):
    assert getattr(api_client, method)(url).status_code == 401
    assert getattr(member_client, method)(url).status_code == 403


@pytest.mark.parametrize("method, url", ENDPOINTS)
def test_editors_without_a_recent_mfa_check_are_refused(editor, client_for, method, url):
    assert getattr(client_for(editor), method)(url).status_code == 403
