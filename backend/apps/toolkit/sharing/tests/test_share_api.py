from datetime import timedelta

import pytest
from django.utils import timezone

from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.ai.research.base import Page, SearchHit
from apps.toolkit.ai.research.fake import FakeResearchProvider
from apps.toolkit.sharing.models import ShareLink
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db


def shares(venture, tail=""):
    return f"{BASE}/ventures/{venture['id']}/shares{tail}"


def public(token):
    return f"{BASE}/public/share/{token}"


def deck_of(client, venture):
    response = client.post(
        f"{BASE}/ventures/{venture['id']}/decks", {"template": "teaser"}, format="json"
    )
    assert response.status_code == 201
    return response.json()


def share(client, venture, subject_type, subject_id, **extra):
    response = client.post(
        shares(venture),
        {"subject_type": subject_type, "subject_id": subject_id, **extra},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def test_a_deck_link_shows_the_deck_without_private_notes(client, api_client, full_venture):
    deck = deck_of(client, full_venture)
    client.patch(
        f"{BASE}/ventures/{full_venture['id']}/decks/{deck['id']}",
        {
            "base_version": 1,
            "ops": [{"op": "replace", "path": "/slides/0/notes", "value": "Do not say this"}],
        },
        format="json",
    )
    made = share(client, full_venture, "deck", deck["id"])
    assert made["token"] and made["url"].endswith(f"/share/{made['token']}")
    response = api_client.get(public(made["token"]))
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["type"] == "deck" and len(body["slides"]) == 5
    assert "notes" not in str(body) and "Do not say this" not in str(body)
    assert response["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert "no-store" in response["Cache-Control"]
    assert ShareLink.objects.get().view_count == 1
    listing = client.get(shares(full_venture)).json()
    assert len(listing) == 1 and "token" not in listing[0] and listing[0]["view_count"] == 1


def test_a_password_link_asks_and_slows_guessing(client, api_client, full_venture):
    deck = deck_of(client, full_venture)
    made = share(client, full_venture, "deck", deck["id"], password="sunrise-42")
    assert made["has_password"] is True
    asked = api_client.get(public(made["token"]))
    assert asked.status_code == 401 and asked.json() == {"password_required": True}
    wrong = api_client.post(public(made["token"]), {"password": "nope"}, format="json")
    assert wrong.status_code == 404
    right = api_client.post(public(made["token"]), {"password": "sunrise-42"}, format="json")
    assert right.status_code == 200 and right.json()["type"] == "deck"
    for _ in range(10):
        api_client.post(public(made["token"]), {"password": "guess"}, format="json")
    blocked = api_client.post(public(made["token"]), {"password": "sunrise-42"}, format="json")
    assert blocked.status_code == 429


def test_unknown_revoked_and_expired_links_look_the_same(client, api_client, full_venture):
    deck = deck_of(client, full_venture)
    first = share(client, full_venture, "deck", deck["id"])
    second = share(client, full_venture, "deck", deck["id"], expires_in_days=1)
    unknown = api_client.get(public("x" * 32))
    assert unknown.status_code == 404

    assert client.delete(shares(full_venture, f"/{first['id']}")).status_code == 204
    revoked = api_client.get(public(first["token"]))
    assert revoked.status_code == 404 and revoked.json() == unknown.json()
    assert client.delete(shares(full_venture, f"/{first['id']}")).status_code == 404

    ShareLink.objects.filter(pk=second["id"]).update(expires_at=timezone.now() - timedelta(hours=1))
    expired = api_client.get(public(second["token"]))
    assert expired.status_code == 404 and expired.json() == unknown.json()


def test_deleting_the_deck_or_the_venture_ends_the_link(client, api_client, full_venture):
    deck = deck_of(client, full_venture)
    made = share(client, full_venture, "deck", deck["id"])
    assert api_client.get(public(made["token"])).status_code == 200
    client.delete(f"{BASE}/ventures/{full_venture['id']}/decks/{deck['id']}")
    assert api_client.get(public(made["token"])).status_code == 404

    other_deck = deck_of(client, full_venture)
    again = share(client, full_venture, "deck", other_deck["id"])
    client.delete(f"{BASE}/ventures/{full_venture['id']}")
    assert api_client.get(public(again["token"])).status_code == 404


def test_the_score_summary_is_shared_without_evidence(client, api_client, full_venture, run_jobs):
    page = Page(
        url="https://data.example.org/x",
        title="Report",
        text="The sector is growing 18 percent a year.",
        publisher="Example",
    )
    FakeResearchProvider.hits["growth"] = [SearchHit(page.url, page.title)]
    FakeResearchProvider.pages[page.url] = page
    FakeLLMProvider.canned["research.extract_facts"] = {"facts": []}
    started = client.post(f"{BASE}/ventures/{full_venture['id']}/score")
    assert started.status_code == 202
    run_jobs()
    made = share(client, full_venture, "score_summary", full_venture["id"])
    body = api_client.get(public(made["token"])).json()
    assert body["type"] == "score_summary" and body["venture_name"] == "Mamapesa"
    assert "evidence" not in str(body) and body["disclaimer"]


def test_a_plan_summary_needs_a_plan(client, full_venture):
    response = client.post(
        shares(full_venture),
        {"subject_type": "plan_summary", "subject_id": full_venture["id"]},
        format="json",
    )
    assert response.status_code == 404


def test_only_the_owner_makes_lists_or_revokes_links(client, other_client, full_venture):
    deck = deck_of(client, full_venture)
    made = share(client, full_venture, "deck", deck["id"])
    assert other_client.get(shares(full_venture)).status_code == 404
    assert (
        other_client.post(
            shares(full_venture),
            {"subject_type": "deck", "subject_id": deck["id"]},
            format="json",
        ).status_code
        == 404
    )
    assert other_client.delete(shares(full_venture, f"/{made['id']}")).status_code == 404
    mine = share(client, full_venture, "deck", deck["id"])
    assert mine["id"] != made["id"]


def test_a_subject_from_another_venture_is_refused(client, full_venture):
    second = client.post(f"{BASE}/ventures", {"name": "Second"}, format="json").json()
    deck = deck_of(client, second)
    response = client.post(
        shares(full_venture),
        {"subject_type": "deck", "subject_id": deck["id"]},
        format="json",
    )
    assert response.status_code == 404


def test_bad_options_are_refused(client, full_venture):
    deck = deck_of(client, full_venture)
    for extra in ({"password": "abc"}, {"expires_in_days": 0}, {"expires_in_days": 400}):
        response = client.post(
            shares(full_venture),
            {"subject_type": "deck", "subject_id": deck["id"], **extra},
            format="json",
        )
        assert response.status_code == 400
    assert ShareLink.objects.count() == 0


def test_anonymous_callers_cannot_manage_links(api_client, full_venture):
    assert api_client.get(shares(full_venture)).status_code == 401
    assert api_client.post(shares(full_venture), {}, format="json").status_code == 401
