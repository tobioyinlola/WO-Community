import pytest

from apps.core import etag
from apps.learning import authoring
from apps.learning.models import Course
from apps.reference.models import CourseCategory

pytestmark = pytest.mark.django_db

CATEGORIES = "/api/v1/admin/reference/course_categories"


@pytest.fixture
def as_admin(make_user, client_for):
    return client_for(make_user(roles=("super_admin",), email="admin@example.com"), mfa_age=5)


@pytest.fixture
def editor(make_user):
    return make_user(roles=("content_editor",), email="editor@example.com")


def course(editor, category):
    return authoring.create_course(
        actor=editor,
        data={
            "title": "Raising a seed round",
            "description": "<p>From first call to close.</p>",
            "instructor": "Onyeka Akumah",
            "category": category,
            "level": "beginner",
        },
    )


def test_the_list_starts_with_the_community_categories(as_admin):
    names = [e["name"] for e in as_admin.get(CATEGORIES).json()]
    for name in (
        "Masterclasses",
        "Investor Classes",
        "Marketing, Sales and Public Relations",
        "Project Management",
        "AI Training",
        "Finance",
    ):
        assert name in names


def test_admins_add_any_category_they_need(as_admin):
    response = as_admin.post(
        CATEGORIES, {"name": "Legal and Compliance", "slug": ""}, format="json"
    )
    assert response.status_code == 201, response.content
    assert CourseCategory.objects.filter(name="Legal and Compliance", active=True).exists()


def test_a_course_takes_the_lists_spelling_and_a_new_name_joins_the_list(editor):
    assert course(editor, "ai training").category == "AI Training"
    assert course(editor, "0-to-1").category == "0-to-1"
    assert CourseCategory.objects.filter(name="0-to-1").exists()


def test_renaming_a_category_renames_it_on_its_courses(as_admin, editor):
    made = course(editor, "Masterclasses")
    entry = CourseCategory.objects.get(name="Masterclasses")
    response = as_admin.patch(
        f"{CATEGORIES}/{entry.pk}", {"name": "Masterclass Series"}, format="json"
    )
    assert response.status_code == 200, response.content
    made.refresh_from_db()
    assert made.category == "Masterclass Series"


def test_a_category_in_use_is_retired_not_deleted(as_admin, editor):
    made = course(editor, "Finance")
    entry = CourseCategory.objects.get(name="Finance")
    assert as_admin.delete(f"{CATEGORIES}/{entry.pk}").status_code == 409
    assert (
        as_admin.patch(f"{CATEGORIES}/{entry.pk}", {"active": False}, format="json").status_code
        == 200
    )
    # A retired category leaves the list offered for new courses; this course keeps it.
    names = [e["name"] for e in as_admin.get(CATEGORIES).json() if e["active"]]
    assert "Finance" not in names
    authoring.update_course(
        actor=editor, course_id=made.pk, data={"category": "Finance"}, if_match=etag.etag_for(made)
    )
    assert Course.objects.get(pk=made.pk).category == "Finance"


def test_course_editors_see_the_categories_to_choose_from(editor, client_for):
    names = [
        c["name"]
        for c in client_for(editor, mfa_age=5).get("/api/v1/admin/course-categories").json()
    ]
    assert "Project Management" in names


def test_a_published_course_moves_to_another_category(editor, client_for, make_user):
    made = course(editor, "0-to-1")
    Course.objects.filter(pk=made.pk).update(status=Course.Status.PUBLISHED)
    client = client_for(editor, mfa_age=5)
    url = f"/api/v1/admin/courses/{made.pk}"
    for target in ("Investor Classes", "AI Training", "0-to-1"):
        tag = client.get(url)["ETag"]
        response = client.patch(url, {"category": target}, format="json", HTTP_IF_MATCH=tag)
        assert response.status_code == 200, response.content
        assert Course.objects.get(pk=made.pk).category == target
    # Members find it under its new category, and no longer under the old one.
    member = client_for(make_user(email="member@example.com"))
    Course.objects.filter(pk=made.pk).update(category="AI Training")
    found = member.get("/api/v1/courses", {"category": "AI Training"}).json()["results"]
    assert [c["title"] for c in found] == ["Raising a seed round"]
    assert member.get("/api/v1/courses", {"category": "0-to-1"}).json()["results"] == []
