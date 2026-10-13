import pytest

from apps.jobs.tests.conftest import post_job
from apps.notifications.models import AdminAlert

pytestmark = pytest.mark.django_db


def test_a_member_job_waiting_for_review_alerts_the_reviewers(poster_client):
    post_job(poster_client)
    alert = AdminAlert.objects.get(kind="job_pending")
    assert alert.path == "/admin/jobs?tab=pending" and "Backend Engineer" in alert.what


def test_a_job_that_goes_live_at_once_does_not(auto_publish, poster_client):
    post_job(poster_client)
    assert not AdminAlert.objects.filter(kind="job_pending").exists()


def test_a_fixed_rejected_job_alerts_again(poster_client, make_user, client_for):
    admin = client_for(make_user(roles=("community_admin",)), mfa_age=5)
    job = post_job(poster_client).json()
    admin.post(f"/api/v1/admin/jobs/{job['id']}/reject", {"reason": "Add pay"}, format="json")
    etag = poster_client.get(f"/api/v1/jobs/{job['id']}")["ETag"]
    poster_client.patch(
        f"/api/v1/jobs/{job['id']}", {"compensation": "NGN 1m"}, format="json", HTTP_IF_MATCH=etag
    )
    assert AdminAlert.objects.filter(kind="job_pending").count() == 2
