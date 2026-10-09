import pytest

from apps.core.models import OutboxEvent
from apps.profiles import services
from apps.profiles.models import FounderProfile
from apps.profiles.tests.conftest import FULL, PROFILE, etag_of, patch

pytestmark = pytest.mark.django_db


# --- reading your own profile ---


def test_anonymous_callers_are_rejected(api_client):
    assert api_client.get(PROFILE).status_code == 401
    assert api_client.patch(PROFILE, {"bio": "x"}).status_code == 401


def test_a_profile_is_created_on_first_use_with_a_slug(my_client, me):
    response = my_client.get(PROFILE)
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(me.pk)
    assert body["slug"].startswith("member-")
    assert body["full_name"] == ""
    assert body["completeness"] == {"score": 0, "next_missing_field": "full_name"}
    assert FounderProfile.objects.filter(user=me).count() == 1


def test_the_owner_view_shows_everything_and_the_visibility_levels(my_client):
    body = my_client.get(PROFILE).json()
    assert body["visibility"] == {
        "basics": "members",
        "bio": "members",
        "location": "members",
        "skills": "members",
        "links": "private",
        "open_to": "members",
    }
    assert {"full_name", "headline", "bio", "country", "city", "skills", "linkedin_url"} <= set(
        body
    )


def test_reads_carry_an_etag_and_are_not_cacheable_by_shared_caches(my_client):
    response = my_client.get(PROFILE)
    assert response["ETag"].startswith('"')
    assert response["Cache-Control"] == "private, no-cache"


def test_pending_accounts_can_fill_in_their_profile(make_user, client_for):
    pending = make_user(email="p@example.com", status="pending")
    client = client_for(pending)
    assert patch(client, {"bio": "Waiting for approval"}).status_code == 200


# --- updating ---


def test_a_full_update_is_saved_and_returned(my_client):
    response = patch(my_client, FULL)
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "ZZNAME Okafor"
    assert body["skills"] == [{"slug": "payments", "name": "Payments"}]
    assert body["custom_skills"] == ["ZZCUSTOMSKILL"]
    assert body["open_to"] == ["hiring"]
    assert body["completeness"] == {"score": 100, "next_missing_field": None}
    assert response["ETag"] != ""


def test_each_save_changes_the_etag(my_client):
    first = etag_of(my_client)
    response = patch(my_client, {"headline": "New headline"}, etag=first)
    assert response["ETag"] != first


def test_partial_updates_leave_other_fields_alone(my_client):
    patch(my_client, FULL)
    patch(my_client, {"headline": "Changed"})
    body = my_client.get(PROFILE).json()
    assert body["headline"] == "Changed"
    assert body["bio"] == "ZZBIO builds things"


def test_fields_can_be_cleared(my_client):
    patch(my_client, FULL)
    patch(my_client, {"headline": "", "skills": [], "custom_skills": [], "linkedin_url": ""})
    body = my_client.get(PROFILE).json()
    assert body["headline"] == "" and body["skills"] == [] and body["linkedin_url"] == ""


def test_a_missing_if_match_header_is_428(my_client):
    response = my_client.patch(PROFILE, {"bio": "x"})
    assert response.status_code == 428
    assert response.json()["code"] == "precondition_required"


def test_a_stale_etag_is_412_and_changes_nothing(my_client):
    stale = etag_of(my_client)
    patch(my_client, {"bio": "first edit"}, etag=stale)  # moves the ETag on
    response = patch(my_client, {"bio": "second edit"}, etag=stale)
    assert response.status_code == 412
    assert response.json()["code"] == "precondition_failed"
    assert my_client.get(PROFILE).json()["bio"] == "first edit"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
@pytest.mark.usefixtures("truncate_audit")
def test_two_edits_from_the_same_version_cannot_both_win(me, client_for):
    import threading

    from django.db import connections

    first = client_for(me)
    etag = first.get(PROFILE)["ETag"]
    results: list[int] = []

    def go(text):
        try:
            results.append(patch(client_for(me), {"bio": text}, etag=etag).status_code)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=go, args=(t,)) for t in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 412]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("full_name", "A"),
        ("full_name", "<b></b>"),
        ("bio", "x" * 501),
        ("headline", "x" * 161),
        ("country", "XX"),
        ("country", "N"),
        ("city", "x" * 101),
        ("skills", ["no-such-skill"]),
        ("skills", ["payments"] * 20),
        ("custom_skills", ["x"] * 11),
        ("custom_skills", ["x" * 41]),
        ("open_to", ["dancing"]),
        ("open_to", "hiring"),
        ("linkedin_url", "https://example.com/in/ada"),
        ("linkedin_url", "http://www.linkedin.com/in/ada"),
        ("x_url", "https://linkedin.com/in/ada"),
        ("website_url", "javascript:alert(1)"),
        ("website_url", "https://127.0.0.1/"),
    ],
)
def test_invalid_values_are_rejected_without_saving(my_client, field, value):
    patch(my_client, {"bio": "keep me"})
    response = patch(my_client, {field: value})
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert field in response.json()["errors"]
    assert my_client.get(PROFILE).json()["bio"] == "keep me"


@pytest.mark.parametrize(
    "field",
    ["slug", "user_id", "user", "completeness_score", "visibility", "photo_key", "id", "badges"],
)
def test_fields_the_member_must_not_control_are_refused(my_client, field):
    response = patch(my_client, {field: "x"})
    assert response.status_code == 400
    assert response.json()["errors"][field] == "Unknown field."


def test_markup_is_stripped_from_text_fields(my_client):
    patch(my_client, {"bio": "Hi <script>alert(1)</script><b>there</b>", "city": "<i>Lagos</i>"})
    body = my_client.get(PROFILE).json()
    assert body["bio"] == "Hi there"
    assert body["city"] == "Lagos"


def test_duplicate_skills_and_open_to_are_collapsed(my_client):
    patch(my_client, {"custom_skills": ["Go", "Go", "<b></b>"], "open_to": ["hiring", "hiring"]})
    body = my_client.get(PROFILE).json()
    assert body["custom_skills"] == ["Go"]
    assert body["open_to"] == ["hiring"]


def test_country_codes_are_normalised_to_upper_case(my_client):
    patch(my_client, {"country": "ng"})
    assert my_client.get(PROFILE).json()["country"] == "NG"


def test_updates_announce_themselves_for_the_directory(my_client, me):
    patch(my_client, {"bio": "changed"})
    event = OutboxEvent.objects.get(topic="profiles.profile_updated")
    assert event.payload == {"user_id": str(me.pk)}


def test_a_member_can_only_ever_change_their_own_profile(my_client, other, me):
    services.get_or_create_profile(other.pk)
    patch(my_client, {"bio": "mine"})
    assert FounderProfile.objects.get(user=other).bio == ""
    assert FounderProfile.objects.get(user=me).bio == "mine"


def test_completeness_rises_as_fields_are_filled_and_names_the_next_gap(my_client):
    patch(my_client, {"full_name": "Ada Obi"})
    assert my_client.get(PROFILE).json()["completeness"] == {
        "score": 15,
        "next_missing_field": "headline",
    }
    patch(my_client, {"headline": "Builder", "bio": "Hello"})
    assert my_client.get(PROFILE).json()["completeness"]["next_missing_field"] == "location"
    assert FounderProfile.objects.get().completeness_score == 50


# --- visibility settings ---


def test_visibility_can_be_read_and_changed(my_client):
    assert my_client.get("/api/v1/me/visibility").json()["bio"] == "members"
    response = my_client.patch("/api/v1/me/visibility", {"bio": "public", "links": "members"})
    assert response.status_code == 200
    assert response.json()["bio"] == "public" and response.json()["links"] == "members"
    assert my_client.get(PROFILE).json()["visibility"]["bio"] == "public"


@pytest.mark.parametrize(
    "body", [{}, {"bio": "everyone"}, {"photo": "public"}, {"bio": 5}, [], {"bio": ["public"]}]
)
def test_invalid_visibility_changes_are_rejected(my_client, body):
    response = my_client.patch("/api/v1/me/visibility", body)
    assert response.status_code == 400
    assert my_client.get(PROFILE).json()["visibility"]["bio"] == "members"


def test_visibility_requires_authentication(api_client):
    assert api_client.get("/api/v1/me/visibility").status_code == 401
    assert api_client.patch("/api/v1/me/visibility", {"bio": "public"}).status_code == 401
