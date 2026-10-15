import pytest

from apps.audit.models import AuditLog
from apps.jobs.models import Job
from apps.jobs.tests.conftest import post_job

pytestmark = pytest.mark.django_db


def test_an_admin_deletes_a_job_for_good_and_it_is_audited(make_user, client_for, poster_client):
    admin = client_for(make_user(roles=("community_admin",), email="admin@example.com"), mfa_age=5)
    job_id = post_job(poster_client).json()["id"]
    assert admin.delete(f"/api/v1/admin/jobs/{job_id}").status_code == 204
    assert not Job.objects.filter(pk=job_id).exists()
    assert AuditLog.objects.filter(action="jobs.delete", target_id=str(job_id)).exists()


def test_a_member_cannot_delete_through_the_console(poster_client):
    job_id = post_job(poster_client).json()["id"]
    assert poster_client.delete(f"/api/v1/admin/jobs/{job_id}").status_code == 403
    assert Job.objects.filter(pk=job_id).exists()
