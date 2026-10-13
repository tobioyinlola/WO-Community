import pytest

from apps.integrations.storage.base import MEDIA
from apps.integrations.storage.fake import FakeStorage
from apps.startups.models import Startup
from apps.startups.tests.conftest import detail, etag_of

pytestmark = pytest.mark.django_db


def logo_url(startup_id):
    return f"{detail(startup_id)}/logo"


def put_logo(client, startup_id, upload_id, etag=None):
    return client.put(
        logo_url(startup_id),
        {"upload_id": str(upload_id)},
        HTTP_IF_MATCH=etag or etag_of(client, startup_id),
    )


def media_exists(base_key):
    return FakeStorage().head(bucket=MEDIA, key=f"{base_key}/large.webp") is not None


def test_an_upload_becomes_the_startup_logo(owner_client, owner, startup_id, ready_upload):
    upload = ready_upload(owner, purpose="startup_logo")
    response = put_logo(owner_client, startup_id, upload.pk)
    assert response.status_code == 200
    assert response.json()["logo"] == {
        "large": f"https://media.test/{upload.base_key}/large.webp",
        "thumb": f"https://media.test/{upload.base_key}/thumb.webp",
    }
    assert Startup.objects.get().logo_key == upload.base_key


def test_a_startup_without_a_logo_has_none(owner_client, startup_id):
    assert owner_client.get(detail(startup_id)).json()["logo"] is None


def test_a_logo_completes_the_startup(owner_client, owner, startup_id, ready_upload):
    owner_client.post(f"{detail(startup_id)}/team", {"email": "mate@example.com"})
    owner_client.put(
        f"{detail(startup_id)}/traction",
        {"metrics": [{"kind": "users", "value": 10}]},
        HTTP_IF_MATCH=etag_of(owner_client, startup_id),
        format="json",
    )
    assert owner_client.get(detail(startup_id)).json()["completeness"]["score"] == 90
    put_logo(owner_client, startup_id, ready_upload(owner, purpose="startup_logo").pk)
    body = owner_client.get(detail(startup_id)).json()
    assert body["completeness"] == {"score": 100, "next_missing_field": None}


def test_other_members_see_the_logo_with_the_basics(
    owner_client, stranger_client, owner, startup_id, ready_upload
):
    put_logo(owner_client, startup_id, ready_upload(owner, purpose="startup_logo").pk)
    logo = stranger_client.get(detail(startup_id)).json()["logo"]
    assert logo["thumb"].startswith("https://media.test/media/startup_logo/")


def test_the_logo_follows_the_basics_visibility(
    owner_client, stranger_client, owner, startup_id, ready_upload
):
    upload = ready_upload(owner, purpose="startup_logo")
    put_logo(owner_client, startup_id, upload.pk)
    owner_client.patch(
        f"{detail(startup_id)}/visibility",
        {"basics": "private"},
        HTTP_IF_MATCH=etag_of(owner_client, startup_id),
    )
    response = stranger_client.get(detail(startup_id))
    assert response.status_code == 404
    assert upload.base_key not in response.content.decode()


# --- who may change it ---


def test_a_founder_on_the_team_can_set_it_with_their_own_upload(
    owner_client, stranger_client, stranger, startup_id, ready_upload
):
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email, "is_founder": True})
    upload = ready_upload(stranger, purpose="startup_logo")
    assert put_logo(stranger_client, startup_id, upload.pk).status_code == 200


def test_an_ordinary_team_member_cannot(
    owner_client, stranger_client, stranger, startup_id, ready_upload
):
    owner_client.post(f"{detail(startup_id)}/team", {"email": stranger.email})
    upload = ready_upload(stranger, purpose="startup_logo")
    response = stranger_client.put(
        logo_url(startup_id),
        {"upload_id": str(upload.pk)},
        HTTP_IF_MATCH=etag_of(stranger_client, startup_id),
    )
    assert response.status_code == 403


def test_outsiders_get_404_and_their_upload_stays_unused(
    stranger_client, stranger, startup_id, ready_upload
):
    upload = ready_upload(stranger, purpose="startup_logo")
    response = stranger_client.put(
        logo_url(startup_id), {"upload_id": str(upload.pk)}, HTTP_IF_MATCH='"x"'
    )
    assert response.status_code == 404
    upload.refresh_from_db()
    assert upload.claimed_at is None


def test_anonymous_callers_get_401(api_client, startup_id):
    assert api_client.put(logo_url(startup_id), {"upload_id": "x"}).status_code == 401
    assert api_client.delete(logo_url(startup_id)).status_code == 401


def test_someone_elses_upload_cannot_be_used(owner_client, stranger, startup_id, ready_upload):
    foreign = ready_upload(stranger, purpose="startup_logo")
    assert put_logo(owner_client, startup_id, foreign.pk).status_code == 400


def test_a_profile_photo_upload_cannot_be_a_logo(owner_client, owner, startup_id, ready_upload):
    photo = ready_upload(owner, purpose="profile_photo")
    assert put_logo(owner_client, startup_id, photo.pk).status_code == 400


def test_the_etag_is_required_and_checked(owner_client, owner, startup_id, ready_upload):
    upload = ready_upload(owner, purpose="startup_logo")
    assert owner_client.put(logo_url(startup_id), {"upload_id": str(upload.pk)}).status_code == 428
    stale = etag_of(owner_client, startup_id)
    owner_client.patch(detail(startup_id), {"pitch": "moves it on"}, HTTP_IF_MATCH=stale)
    assert put_logo(owner_client, startup_id, upload.pk, etag=stale).status_code == 412


def test_the_logo_cannot_be_set_through_the_startup_update(owner_client, startup_id):
    response = owner_client.patch(
        detail(startup_id), {"logo_key": "media/x"}, HTTP_IF_MATCH=etag_of(owner_client, startup_id)
    )
    assert response.status_code == 400


# --- replacing and removing ---


def test_replacing_and_removing_delete_the_old_files(
    owner_client, owner, startup_id, ready_upload, django_capture_on_commit_callbacks
):
    first = ready_upload(owner, purpose="startup_logo")
    put_logo(owner_client, startup_id, first.pk)
    second = ready_upload(owner, purpose="startup_logo")
    with django_capture_on_commit_callbacks(execute=True):
        put_logo(owner_client, startup_id, second.pk)
    assert not media_exists(first.base_key) and media_exists(second.base_key)

    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.delete(
            logo_url(startup_id), HTTP_IF_MATCH=etag_of(owner_client, startup_id)
        )
    assert response.status_code == 200 and response.json()["logo"] is None
    assert not media_exists(second.base_key)
    assert Startup.objects.get().logo_key == ""


def test_removing_needs_the_etag(owner_client, owner, startup_id, ready_upload):
    put_logo(owner_client, startup_id, ready_upload(owner, purpose="startup_logo").pk)
    assert owner_client.delete(logo_url(startup_id)).status_code == 428
