import pytest

from apps.integrations.email.fake import FakeEmailAdapter
from apps.notifications import adminalerts
from apps.notifications.models import AdminAlert
from apps.support.tests.helpers import TICKETS, active, body

pytestmark = pytest.mark.django_db


def test_a_new_request_alerts_support_admins_and_confirms_to_the_member(
    make_user, client_for, run_outbox
):
    FakeEmailAdapter.reset()
    ada = active(make_user, "ada@example.com", "Ada")
    active(make_user, "support@example.com", roles=("community_admin",))
    response = client_for(ada).post(TICKETS, body(), format="json")
    assert response.status_code == 201
    run_outbox()
    alert = AdminAlert.objects.get(kind="support_ticket")
    assert alert.who == "ada@example.com" and alert.path.startswith("/admin/support?ticket=")
    adminalerts.dispatch("support_ticket")
    by_recipient = {m.to: m for m in FakeEmailAdapter.sent}
    assert "Open the request" in by_recipient["support@example.com"].html_body
    received = by_recipient["ada@example.com"]
    assert received.subject.startswith("We've got your request")
    assert received.html_body and received.no_reply
