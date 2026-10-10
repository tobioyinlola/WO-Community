import pytest

from apps.directory.tests.conftest import FOUNDERS, STARTUPS, edit_startup, set_startup_levels

pytestmark = pytest.mark.django_db


def found(client, q, url=STARTUPS, **extra):
    response = client.get(url, {"q": q, **extra})
    assert response.status_code == 200
    key = "name" if url == STARTUPS else "full_name"
    return [item[key] for item in response.json()["results"]]


@pytest.fixture
def catalogue(listed):
    return {
        "zentrix": listed(
            "Zentrix Lending",
            founder="Chidi Okeke",
            pitch="Micro loans for market traders",
            description="ZZDESCRIPTION lending without paperwork",
        ),
        "agro": listed(
            "FarmLink",
            founder="Wanjiru Kamau",
            sector="agritech",
            country="KE",
            pitch="Connecting farmers to buyers",
            description="Cold chain logistics for tomatoes",
        ),
        "health": listed(
            "Clinic Hub",
            founder="Kwame Mensah",
            sector="healthtech",
            country="GH",
            pitch="Book doctors by phone",
            description="Appointments across Accra",
        ),
    }


def test_search_finds_a_startup_by_its_name(api_client, catalogue):
    assert found(api_client, "Zentrix") == ["Zentrix Lending"]
    assert found(api_client, "zentrix lending") == ["Zentrix Lending"]


def test_search_finds_partial_words_in_a_name(api_client, catalogue):
    assert found(api_client, "Zentr") == ["Zentrix Lending"]
    assert found(api_client, "farm") == ["FarmLink"]


def test_search_tolerates_a_typo_in_a_name(api_client, catalogue):
    assert "Zentrix Lending" in found(api_client, "Zentrx Lendng")


def test_search_reads_the_pitch_the_description_and_the_sector(api_client, catalogue):
    assert found(api_client, "farmers") == ["FarmLink"]
    assert found(api_client, "tomatoes") == ["FarmLink"]
    assert found(api_client, "healthtech") == ["Clinic Hub"]
    assert found(api_client, "Accra") == ["Clinic Hub"]


def test_search_finds_a_startup_by_its_public_founder(api_client, catalogue):
    assert found(api_client, "Wanjiru") == ["FarmLink"]


def test_search_combines_with_filters(api_client, catalogue):
    assert found(api_client, "Hub", country="GH") == ["Clinic Hub"]
    assert found(api_client, "Hub", country="KE") == []


def test_a_name_match_outranks_a_mention_in_a_description(api_client, listed):
    listed("Quiet Co", description="ZZDESCRIPTION we love lending")
    listed("Lending Works")
    assert found(api_client, "lending")[0] == "Lending Works"


def test_no_match_gives_an_empty_page(api_client, catalogue):
    body = api_client.get(STARTUPS, {"q": "xylophone"}).json()
    assert body == {"results": [], "next_cursor": None}


def test_a_search_returns_its_best_matches_without_a_cursor(api_client, listed):
    for n in range(5):
        listed(f"Lending {n}")
    body = api_client.get(STARTUPS, {"q": "lending", "limit": 3}).json()
    assert len(body["results"]) == 3 and body["next_cursor"] is None


@pytest.mark.parametrize(
    "q",
    [
        "'; DROP TABLE directory_publicstartup; --",
        '" OR 1=1 --',
        "a & b | !c",
        "%",
        "_",
        "\\",
        "(((",
    ],
)
def test_hostile_or_odd_input_is_just_text(api_client, catalogue, q):
    assert api_client.get(STARTUPS, {"q": q}).status_code == 200
    assert api_client.get(STARTUPS).json()["results"]  # tables intact


def test_quotes_and_operators_in_the_websearch_style_work(api_client, catalogue):
    assert found(api_client, '"cold chain"') == ["FarmLink"]
    assert found(api_client, "lending -zentrix") == []


def test_blank_and_padded_queries_behave_like_browsing(api_client, catalogue):
    assert len(found(api_client, "")) == 3
    assert found(api_client, "   Zentrix   ") == ["Zentrix Lending"]


def test_searches_are_limited_to_sixty_a_minute_but_browsing_is_not(
    api_client, catalogue, monkeypatch
):
    from apps.directory.views import SearchThrottle

    monkeypatch.setattr(SearchThrottle, "THROTTLE_RATES", {"public_search": "2/min"})
    assert [api_client.get(STARTUPS, {"q": "farm"}).status_code for _ in range(3)] == [
        200,
        200,
        429,
    ]
    assert api_client.get(STARTUPS).status_code == 200


# --- search never reaches private data (AC-17) ---


def test_a_private_description_cannot_be_found_by_searching_for_it(api_client, listed):
    listed("Secretive Co", description="ZZUNIQUETERM roadmap", description_public=False)
    assert found(api_client, "ZZUNIQUETERM") == []


def test_hiding_the_description_removes_it_from_search_after_the_next_refresh(
    api_client, listed, run_outbox
):
    fixture = listed("Open Co", description="ZZUNIQUETERM roadmap")
    assert found(api_client, "ZZUNIQUETERM") == ["Open Co"]
    set_startup_levels(fixture.id, description="members")
    run_outbox()
    assert found(api_client, "ZZUNIQUETERM") == []


def test_a_founder_whose_name_is_not_public_cannot_be_found_through_the_startup(api_client, listed):
    listed("Plain Co", founder="Hidden Person", founder_public=False)
    assert found(api_client, "Hidden") == []
    assert found(api_client, "Hidden", url=FOUNDERS) == []


def test_a_private_team_list_keeps_founder_names_out_of_startup_search(api_client, listed):
    listed("Plain Co", founder="Quiet Person", team_public=False)
    assert found(api_client, "Quiet") == []


def test_private_profile_fields_are_not_searchable(api_client, listed):
    listed("Plain Co", founder="Ada Obi")  # the bio is "ZZBIO builds things" but members-only
    assert found(api_client, "ZZBIO", url=FOUNDERS) == []


def test_unlisted_startups_are_not_searchable(api_client, listed):
    listed("Hidden Co", listed=False)
    assert found(api_client, "Hidden") == []


# --- founders ---


def test_founders_are_found_by_name_skill_and_startup(api_client, catalogue):
    assert found(api_client, "Chidi", url=FOUNDERS) == ["Chidi Okeke"]
    assert found(api_client, "payments", url=FOUNDERS)  # a public skill
    assert found(api_client, "FarmLink", url=FOUNDERS) == ["Wanjiru Kamau"]


def test_edits_reach_search_once_the_refresh_has_run(api_client, listed, run_outbox):
    fixture = listed("Old Name")
    assert found(api_client, "Rebranded") == []
    edit_startup(fixture.id, name="Rebranded Co")
    assert found(api_client, "Rebranded") == []  # not yet: it travels through the outbox
    run_outbox()
    assert found(api_client, "Rebranded") == ["Rebranded Co"]
    assert found(api_client, "Old Name") == []
