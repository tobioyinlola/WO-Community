import pytest

from apps.core.models import OutboxEvent
from apps.integrations.storage.base import MEDIA
from apps.integrations.storage.fake import FakeStorage
from apps.profiles.models import FounderProfile
from apps.profiles.tests.conftest import PROFILE, etag_of, member_url, patch
from apps.uploads.models import Upload

pytestmark = pytest.mark.django_db

PHOTO = "/api/v1/me/profile/photo"


def put_photo(client, upload_id, etag=None):
    return client.put(PHOTO, {"upload_id": str(upload_id)}, HTTP_IF_MATCH=etag or etag_of(client))


def delete_photo(client, etag=None):
    return client.delete(PHOTO, HTTP_IF_MATCH=etag or etag_of(client))


def media_exists(base_key):
    return FakeStorage().head(bucket=MEDIA, key=f"{base_key}/large.webp") is not None


def test_a_ready_upload_becomes_the_profile_photo(my_client, me, ready_upload):
    upload = ready_upload(me)
    response = put_photo(my_client, upload.pk)
    assert response.status_code == 200
    photo = response.json()["photo"]
    assert photo == {
        "large": f"https://media.test/{upload.base_key}/large.webp",
        "thumb": f"https://media.test/{upload.base_key}/thumb.webp",
    }
    assert FounderProfile.objects.get(user=me).photo_key == upload.base_key
    assert response["ETag"]
    assert Upload.objects.get().claimed_at is not None


def test_a_profile_without_a_photo_says_so(my_client):
    assert my_client.get(PROFILE).json()["photo"] is None


def test_a_photo_raises_the_completeness_score(my_client, me, ready_upload):
    before = my_client.get(PROFILE).json()["completeness"]["score"]
    put_photo(my_client, ready_upload(me).pk)
    assert my_client.get(PROFILE).json()["completeness"]["score"] == before + 15


def test_the_etag_is_required_and_checked(my_client, me, ready_upload):
    upload = ready_upload(me)
    assert my_client.put(PHOTO, {"upload_id": str(upload.pk)}).status_code == 428
    stale = etag_of(my_client)
    patch(my_client, {"bio": "moves the etag on"})
    assert put_photo(my_client, upload.pk, etag=stale).status_code == 412
    assert FounderProfile.objects.get(user=me).photo_key == ""


def test_other_members_see_the_photo_as_part_of_the_basics(
    my_client, other_client, me, ready_upload
):
    put_photo(my_client, ready_upload(me).pk)
    body = other_client.get(member_url(me)).json()
    assert body["photo"]["thumb"].startswith("https://media.test/media/profile_photo/")


def test_hiding_the_basics_hides_the_photo_too(my_client, other_client, me, ready_upload):
    upload = ready_upload(me)
    put_photo(my_client, upload.pk)
    my_client.patch("/api/v1/me/visibility", {"basics": "private"})
    response = other_client.get(member_url(me))
    assert response.status_code == 404
    assert upload.base_key not in response.content.decode()


def test_the_public_audience_sees_the_photo_only_with_public_basics(my_client, me, ready_upload):
    from apps.core.visibility import Audience
    from apps.profiles import selectors

    put_photo(my_client, ready_upload(me).pk)
    profile = FounderProfile.objects.get(user=me)
    assert selectors.project_profile(profile, Audience.PUBLIC) is None
    my_client.patch("/api/v1/me/visibility", {"basics": "public"})
    profile.refresh_from_db()
    assert selectors.project_profile(profile, Audience.PUBLIC)["photo"] is not None


# --- whose uploads can be used ---


def test_someone_elses_upload_cannot_be_used(my_client, other, ready_upload):
    foreign = ready_upload(other)
    response = put_photo(my_client, foreign.pk)
    assert response.status_code == 400
    assert "upload_id" in response.json()["errors"]
    assert Upload.objects.get().claimed_at is None


def test_an_upload_made_for_a_logo_cannot_be_a_photo(my_client, me, ready_upload):
    logo = ready_upload(me, purpose="startup_logo")
    assert put_photo(my_client, logo.pk).status_code == 400


def test_an_upload_that_is_not_ready_cannot_be_used(my_client, me):
    from apps.uploads import services

    upload, _ = services.request_upload(
        owner_id=me.pk, purpose="profile_photo", content_type="image/png", size=1000
    )
    assert put_photo(my_client, upload.pk).status_code == 400


def test_unknown_and_malformed_ids_are_refused(my_client):
    assert put_photo(my_client, "00000000-0000-0000-0000-000000000000").status_code == 400
    response = my_client.put(PHOTO, {"upload_id": "nope"}, HTTP_IF_MATCH=etag_of(my_client))
    assert response.status_code == 400


def test_an_upload_can_only_be_used_once(my_client, me, ready_upload):
    upload = ready_upload(me)
    put_photo(my_client, upload.pk)
    again = put_photo(my_client, upload.pk)
    assert again.status_code == 400
    assert "already in use" in str(again.json()["errors"])


def test_the_photo_cannot_be_set_through_the_profile_update(my_client):
    for field in ("photo", "photo_key"):
        assert patch(my_client, {field: "media/x"}).status_code == 400


def test_the_photo_endpoint_needs_a_login(api_client):
    assert api_client.put(PHOTO, {"upload_id": "x"}).status_code == 401
    assert api_client.delete(PHOTO).status_code == 401


# --- replacing and removing ---


def test_replacing_the_photo_deletes_the_old_files(
    my_client, me, ready_upload, django_capture_on_commit_callbacks
):
    first = ready_upload(me)
    put_photo(my_client, first.pk)
    second = ready_upload(me)
    with django_capture_on_commit_callbacks(execute=True):
        assert put_photo(my_client, second.pk).status_code == 200
    assert not media_exists(first.base_key)
    assert media_exists(second.base_key)
    first.refresh_from_db()
    assert first.status == "discarded"
    assert FounderProfile.objects.get(user=me).photo_key == second.base_key


def test_removing_the_photo_deletes_its_files_and_lowers_the_score(
    my_client, me, ready_upload, django_capture_on_commit_callbacks
):
    baseline = my_client.get(PROFILE).json()["completeness"]["score"]
    upload = ready_upload(me)
    put_photo(my_client, upload.pk)
    with django_capture_on_commit_callbacks(execute=True):
        response = delete_photo(my_client)
    assert response.status_code == 200 and response.json()["photo"] is None
    assert not media_exists(upload.base_key)
    assert response.json()["completeness"]["score"] == baseline


def test_removing_needs_the_etag(my_client, me, ready_upload):
    put_photo(my_client, ready_upload(me).pk)
    assert my_client.delete(PHOTO).status_code == 428


def test_changing_the_photo_announces_the_change_for_the_directory(my_client, me, ready_upload):
    put_photo(my_client, ready_upload(me).pk)
    assert OutboxEvent.objects.filter(topic="profiles.profile_updated").exists()
