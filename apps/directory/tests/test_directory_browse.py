import json

import pytest

from apps.directory.pagination import decode_cursor, encode_cursor, rows_after
from apps.directory.tests.conftest import FOUNDERS, SITEMAP, STARTUPS, slugs

pytestmark = pytest.mark.django_db


# --- access and caching ---


def test_the_directory_needs_no_login(api_client, listed):
    listed()
    assert api_client.get(STARTUPS).status_code == 200
    assert api_client.get(FOUNDERS).status_code == 200
    assert api_client.get(SITEMAP).status_code == 200


def test_a_bad_authorization_header_is_ignored_not_rejected(api_client, listed):
    listed()
    response = api_client.get(STARTUPS, HTTP_AUTHORIZATION="Bearer not-a-token")
    assert response.status_code == 200


def test_signed_in_members_get_exactly_what_visitors_get(api_client, client_for, listed):
    fixture = listed()
    visitor = api_client.get(STARTUPS).json()
    member = client_for(fixture.user).get(STARTUPS).json()
    assert visitor == member


def test_pages_are_cacheable_with_an_etag_and_support_conditional_requests(api_client, listed):
    listed()
    first = api_client.get(STARTUPS)
    assert first["Cache-Control"] == (
        "public, max-age=300, stale-while-revalidate=600, stale-if-error=86400"
    )
    tag = first["ETag"]
    assert tag.startswith('"')
    second = api_client.get(STARTUPS, HTTP_IF_NONE_MATCH=tag)
    assert second.status_code == 304
    assert second.content == b""
    assert second["ETag"] == tag


def test_the_etag_changes_when_the_content_changes(api_client, listed):
    listed("One Co")
    before = api_client.get(STARTUPS)["ETag"]
    listed("Two Co")
    after = api_client.get(STARTUPS)
    assert after["ETag"] != before
    assert api_client.get(STARTUPS, HTTP_IF_NONE_MATCH=before).status_code == 200


def test_responses_set_no_cookies(api_client, listed):
    listed()
    assert not api_client.get(STARTUPS).cookies


# --- what a card contains ---


def test_a_card_has_the_directory_fields_and_nothing_else(api_client, listed):
    listed("Acme Pay", founder="Ada Obi")
    card = api_client.get(STARTUPS).json()["results"][0]
    assert set(card) == {
        "slug",
        "name",
        "pitch",
        "sector",
        "stage",
        "country",
        "city",
        "year_founded",
        "featured",
        "founders",
    }
    assert card["name"] == "Acme Pay"
    assert card["sector"] == {"slug": "fintech", "name": "Fintech"}
    assert card["founders"] == [{"slug": card["founders"][0]["slug"], "full_name": "Ada Obi"}]


def test_unlisted_startups_are_absent(api_client, listed):
    listed("Hidden Co", listed=False)
    listed("Shown Co")
    names = [c["name"] for c in api_client.get(STARTUPS).json()["results"]]
    assert names == ["Shown Co"]


def test_nothing_in_any_response_contains_a_contact_address(api_client, listed):
    fixture = listed()
    texts = [
        api_client.get(STARTUPS).content,
        api_client.get(f"{STARTUPS}/{fixture.slug}").content,
        api_client.get(FOUNDERS).content,
        api_client.get(SITEMAP).content,
    ]
    for text in texts:
        assert b"@example.com" not in text
        assert b"email" not in text


# --- filters ---


@pytest.fixture
def mixed(listed):
    return {
        "ng_fin": listed(
            "Naija Pay", country="NG", sector="fintech", stage="seed", founder_location_public=True
        ),
        "ke_health": listed(
            "Kenya Care",
            country="KE",
            sector="healthtech",
            stage="series-a",
            skills=("marketing",),
            founder_location_public=True,
        ),
        "gh_fin": listed(
            "Ghana Cash",
            country="GH",
            sector="fintech",
            stage="pre-seed",
            skills=("payments", "sales"),
            founder_location_public=True,
        ),
    }


def names(response):
    return {c["name"] for c in response.json()["results"]}


def test_filter_by_country(api_client, mixed):
    assert names(api_client.get(STARTUPS, {"country": "KE"})) == {"Kenya Care"}
    assert names(api_client.get(STARTUPS, {"country": "ng"})) == {"Naija Pay"}


def test_filter_by_sector_and_stage(api_client, mixed):
    assert names(api_client.get(STARTUPS, {"sector": "fintech"})) == {"Naija Pay", "Ghana Cash"}
    assert names(api_client.get(STARTUPS, {"stage": "series-a"})) == {"Kenya Care"}
    assert names(api_client.get(STARTUPS, {"sector": "fintech", "stage": "seed"})) == {"Naija Pay"}


def test_filter_by_founder_skills_requires_all_of_them(api_client, mixed):
    assert names(api_client.get(STARTUPS, {"skills": "payments"})) == {"Naija Pay", "Ghana Cash"}
    assert names(api_client.get(STARTUPS, {"skills": "payments,sales"})) == {"Ghana Cash"}
    assert names(api_client.get(STARTUPS, {"skills": "payments,marketing"})) == set()


def test_filters_that_match_nothing_return_an_empty_page(api_client, mixed):
    body = api_client.get(STARTUPS, {"country": "ZA"}).json()
    assert body == {"results": [], "next_cursor": None}


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 51},
        {"limit": "many"},
        {"sort": "popularity"},
        {"sector": "not a slug"},
        {"country": "NIGERIA"},
        {"skills": "a,b,c,d,e,f"},
        {"skills": "bad slug!"},
        {"featured": "maybe"},
        {"q": "x" * 101},
        {"order": "name"},
        {"owner": "someone"},
    ],
)
def test_bad_parameters_are_rejected_not_ignored(api_client, listed, params):
    listed()
    assert api_client.get(STARTUPS, params).status_code == 400


def test_founders_can_be_filtered_by_country_and_skill(api_client, mixed):
    assert len(api_client.get(FOUNDERS).json()["results"]) == 3
    assert len(api_client.get(FOUNDERS, {"country": "GH"}).json()["results"]) == 1
    assert len(api_client.get(FOUNDERS, {"skills": "marketing"}).json()["results"]) == 1
    assert api_client.get(FOUNDERS, {"sector": "fintech"}).status_code == 400


# --- ordering and paging ---


def test_newest_first_by_default_with_featured_pinned_on_top(api_client, listed):
    listed("Old Co")
    listed("Middle Co")
    listed("Pinned Co", featured=True)
    listed("New Co")
    result = [c["name"] for c in api_client.get(STARTUPS).json()["results"]]
    assert result == ["Pinned Co", "New Co", "Middle Co", "Old Co"]


def test_alphabetical_order_keeps_featured_on_top(api_client, listed):
    listed("Bravo")
    listed("Alpha")
    listed("Charlie", featured=True)
    result = [
        c["name"] for c in api_client.get(STARTUPS, {"sort": "alphabetical"}).json()["results"]
    ]
    assert result == ["Charlie", "Alpha", "Bravo"]


def test_alphabetical_order_ignores_case(api_client, listed):
    listed("zeta")
    listed("Alpha")
    listed("beta")
    result = [
        c["name"] for c in api_client.get(STARTUPS, {"sort": "alphabetical"}).json()["results"]
    ]
    assert result == ["Alpha", "beta", "zeta"]


def test_the_featured_filter_lists_only_pinned_startups(api_client, listed):
    listed("Plain")
    listed("Star", featured=True)
    assert names(api_client.get(STARTUPS, {"featured": "true"})) == {"Star"}


@pytest.mark.parametrize("sort", ["newest", "alphabetical"])
def test_paging_visits_every_startup_once_in_order(api_client, listed, sort):
    for n in range(7):
        listed(f"Company {n}", featured=(n == 3))
    full = slugs(api_client.get(STARTUPS, {"sort": sort, "limit": 50}))
    collected, cursor = [], ""
    for _ in range(10):
        page = api_client.get(STARTUPS, {"sort": sort, "limit": 3, "cursor": cursor}).json()
        collected += [c["slug"] for c in page["results"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert collected == full
    assert len(set(collected)) == 7


def test_the_last_page_has_no_cursor_and_exact_pages_do_not_invent_one(api_client, listed):
    for n in range(4):
        listed(f"Company {n}")
    page = api_client.get(STARTUPS, {"limit": 4}).json()
    assert len(page["results"]) == 4 and page["next_cursor"] is None


def test_new_listings_do_not_disturb_a_reader_part_way_through(api_client, listed):
    for n in range(4):
        listed(f"Company {n}")
    original = slugs(api_client.get(STARTUPS, {"limit": 50}))
    first = api_client.get(STARTUPS, {"limit": 2}).json()
    listed("Latecomer")  # newer than everything already read
    second = api_client.get(STARTUPS, {"limit": 2, "cursor": first["next_cursor"]}).json()
    read = [c["slug"] for c in first["results"]] + [c["slug"] for c in second["results"]]
    assert read == original[:4]


@pytest.mark.parametrize("cursor", ["garbage", "e30", "eyJ2IjogWzFdfQ", "!!!", "a" * 399])
def test_damaged_cursors_are_a_400(api_client, listed, cursor):
    listed()
    response = api_client.get(STARTUPS, {"cursor": cursor})
    assert response.status_code == 400
    assert "cursor" in response.json()["errors"]


def test_a_cursor_cannot_be_used_with_a_different_sort(api_client, listed):
    for n in range(3):
        listed(f"Company {n}")
    cursor = api_client.get(STARTUPS, {"limit": 1}).json()["next_cursor"]
    response = api_client.get(STARTUPS, {"sort": "alphabetical", "cursor": cursor})
    assert response.status_code == 400


def test_a_forged_cursor_with_wrong_types_is_refused(api_client, listed):
    listed()
    forged = encode_cursor("newest", ["x", "y", "z"])
    assert api_client.get(STARTUPS, {"cursor": forged}).status_code == 400


def test_a_well_formed_cursor_round_trips():
    key = "01a12243-be20-7a9e-b3f5-34276441d674"
    fields = ("featured_rank", "newest_key", "id")
    values = decode_cursor(encode_cursor("newest", [1, -5, key]), "newest", fields)
    assert [str(v) for v in values] == ["1", "-5", key]


def test_keyset_condition_has_one_branch_per_column():
    condition = rows_after(("a", "b", "id"), [1, 2, 3])
    assert len(condition.children) == 3  # a>1, or a=1 and b>2, or a=1 and b=2 and id>3


# --- founders ---


def test_founders_page_through_in_both_orders(api_client, listed):
    for n in range(5):
        listed(f"Company {n}", founder=f"Founder {n}")
    for sort in ("newest", "alphabetical"):
        full = slugs(api_client.get(FOUNDERS, {"sort": sort, "limit": 50}))
        got, cursor = [], ""
        while True:
            page = api_client.get(FOUNDERS, {"sort": sort, "limit": 2, "cursor": cursor}).json()
            got += [c["slug"] for c in page["results"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert got == full and len(got) == 5


# --- cost ---


def test_listing_uses_a_fixed_number_of_queries(api_client, listed, django_assert_max_num_queries):
    for n in range(6):
        listed(f"Company {n}")
    with django_assert_max_num_queries(3):
        assert api_client.get(STARTUPS, {"limit": 50}).status_code == 200
    with django_assert_max_num_queries(3):
        assert api_client.get(FOUNDERS, {"limit": 50}).status_code == 200


def test_cached_pages_serialise_to_stable_json(api_client, listed):
    listed()
    one = api_client.get(STARTUPS).content
    two = api_client.get(STARTUPS).content
    assert json.loads(one) == json.loads(two)
