import pytest
from django.utils import timezone

from apps.startups.models import StartupMember
from apps.startups.tests.conftest import detail

pytestmark = pytest.mark.django_db


def team_url(startup_id):
    return f"{detail(startup_id)}/team"


def add(client, startup_id, email, **extra):
    return client.post(team_url(startup_id), {"email": email, **extra})


# --- adding ---


def test_the_owner_can_add_an_existing_member_by_email(owner_client, startup_id, stranger):
    response = add(owner_client, startup_id, "Stranger@Example.com", title="CTO")
    assert response.status_code == 201
    body = response.json()
    assert (body["email"], body["title"], body["is_founder"]) == (
        "stranger@example.com",
        "CTO",
        False,
    )
    assert StartupMember.objects.get(user=stranger).title == "CTO"


def test_the_answer_is_the_same_whether_or_not_the_address_has_an_account(
    owner_client, startup_id, stranger
):
    known = add(owner_client, startup_id, stranger.email).json()
    unknown = add(owner_client, startup_id, "nobody@example.com").json()
    assert set(known) == set(unknown) == {"id", "email", "title", "is_founder"}
    unlinked = StartupMember.objects.get(invited_email="nobody@example.com")
    assert unlinked.user is None


def test_the_owner_team_view_does_not_reveal_which_addresses_have_accounts(
    owner_client, startup_id, stranger
):
    add(owner_client, startup_id, stranger.email)
    add(owner_client, startup_id, "nobody@example.com")
    team = owner_client.get(detail(startup_id)).json()["team"]
    assert all(set(m) == {"id", "email", "title", "is_founder"} for m in team)


def test_adding_the_same_address_twice_is_a_conflict(owner_client, startup_id):
    add(owner_client, startup_id, "mate@example.com")
    again = add(owner_client, startup_id, "MATE@example.com")
    assert again.status_code == 409
    assert again.json()["code"] == "already_on_team"


def test_a_pending_account_is_not_attached_until_approved(owner_client, startup_id, make_user):
    make_user(email="soon@example.com", status="pending", email_verified_at=timezone.now())
    add(owner_client, startup_id, "soon@example.com")
    assert StartupMember.objects.get(invited_email="soon@example.com").user is None


def test_approving_a_member_attaches_them_to_teams_that_listed_them(
    owner_client, startup_id, make_user, run_outbox
):
    from apps.accounts import events as account_events
    from apps.core import events as domain_events

    joiner = make_user(
        email="joiner@example.com", status="active", email_verified_at=timezone.now()
    )
    add(owner_client, startup_id, "joiner@example.com")
    StartupMember.objects.filter(invited_email="joiner@example.com").update(user=None)
    domain_events.publish(account_events.MemberApproved(user_id=str(joiner.pk)))
    run_outbox()
    assert StartupMember.objects.get(invited_email="joiner@example.com").user == joiner


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email"},
        {"email": ""},
        {"email": "a@example.com", "title": "x" * 81},
        {"email": "a@example.com", "is_founder": "maybe"},
        {"email": "a@example.com", "user": "someone"},
        {},
    ],
)
def test_invalid_team_requests_are_rejected(owner_client, startup_id, body):
    assert owner_client.post(team_url(startup_id), body).status_code == 400


def test_only_the_owner_can_add_people(owner_client, stranger_client, startup_id, stranger):
    add(owner_client, startup_id, stranger.email, is_founder=True)
    assert add(stranger_client, startup_id, "x@example.com").status_code == 403


def test_outsiders_cannot_add_people_and_learn_nothing(stranger_client, startup_id):
    assert add(stranger_client, startup_id, "x@example.com").status_code == 404


def test_team_changes_need_authentication(api_client, startup_id):
    assert add(api_client, startup_id, "x@example.com").status_code == 401


# --- removing ---


def member_id(email):
    return StartupMember.objects.get(invited_email=email).pk


def test_the_owner_can_remove_a_member(owner_client, startup_id):
    add(owner_client, startup_id, "mate@example.com")
    response = owner_client.delete(f"{team_url(startup_id)}/{member_id('mate@example.com')}")
    assert response.status_code == 204
    assert not StartupMember.objects.filter(invited_email="mate@example.com").exists()


def test_members_can_remove_themselves(owner_client, stranger_client, startup_id, stranger):
    add(owner_client, startup_id, stranger.email)
    mid = member_id(stranger.email)
    assert stranger_client.delete(f"{team_url(startup_id)}/{mid}").status_code == 204
    assert not StartupMember.objects.filter(user=stranger).exists()


def test_members_cannot_remove_each_other(
    owner_client, stranger_client, startup_id, stranger, make_user, client_for
):
    third = make_user(email="third@example.com", approved_at=timezone.now())
    add(owner_client, startup_id, stranger.email)
    add(owner_client, startup_id, third.email)
    response = stranger_client.delete(f"{team_url(startup_id)}/{member_id(third.email)}")
    assert response.status_code == 404
    assert StartupMember.objects.filter(user=third).exists()


def test_the_owner_cannot_be_removed(owner_client, startup_id, owner):
    mid = StartupMember.objects.get(user=owner).pk
    response = owner_client.delete(f"{team_url(startup_id)}/{mid}")
    assert response.status_code == 409
    assert response.json()["code"] == "is_owner"


def test_removing_from_another_startup_is_404(owner_client, startup_id, stranger_client):
    from apps.startups.tests.conftest import STARTUPS, new_startup_body

    other = stranger_client.post(STARTUPS, new_startup_body(name="Other Co")).json()["id"]
    foreign = StartupMember.objects.filter(startup_id=other).first().pk
    assert owner_client.delete(f"{team_url(startup_id)}/{foreign}").status_code == 404
    assert StartupMember.objects.filter(pk=foreign).exists()


def test_removal_requires_authentication(api_client, owner_client, startup_id):
    add(owner_client, startup_id, "mate@example.com")
    mid = member_id("mate@example.com")
    assert api_client.delete(f"{team_url(startup_id)}/{mid}").status_code == 401
