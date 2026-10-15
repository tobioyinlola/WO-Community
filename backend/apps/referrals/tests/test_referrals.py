import pytest
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts import referrals
from apps.accounts.models import User
from apps.accounts.tests.helpers import REGISTER_URL, registration_payload
from apps.audit.models import AuditLog
from apps.profiles.models import FounderProfile
from apps.profiles.services import get_or_create_profile
from apps.referrals import selectors

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/members/search-referrer"
MINE = "/api/v1/me/referrals"
SUMMARY = "/api/v1/admin/referrals/summary"
TOP = "/api/v1/admin/referrals/top"


def member(make_user, email, name="", public=True, **fields):
    user = make_user(
        email=email, approved_at=timezone.now(), email_verified_at=timezone.now(), **fields
    )
    user.status = "active"
    user.save(update_fields=["status"])
    if name:
        profile = get_or_create_profile(user.pk)
        FounderProfile.objects.filter(pk=profile.pk).update(
            full_name=name, visibility={"basics": "public" if public else "members"}
        )
    return user


@pytest.fixture
def ada(make_user):
    return member(make_user, "ada@example.com", "Adaeze Okafor")


@pytest.fixture
def admin(make_user, client_for):
    user = make_user(roles=("community_admin",), email="admin@example.com")
    return client_for(user, mfa_age=5)


def register(api_client, **referral):
    body = registration_payload(referral=referral) if referral else registration_payload()
    response = api_client.post(REGISTER_URL, body, format="json")
    assert response.status_code == 202, response.content
    return User.objects.get(email="new.member@example.com")


# --- codes ---


def test_every_new_account_gets_a_short_code_nobody_else_has(make_user):
    codes = {make_user(email=f"u{n}@example.com").pk: None for n in range(3)}
    created = [User.objects.create_user(f"c{n}@example.com", "x") for n in range(3)]
    values = [u.referral_code for u in created]
    assert all(len(v) == 8 and set(v) <= set(referrals.ALPHABET) for v in values)
    assert len(set(values)) == 3 and codes


def test_the_alphabet_leaves_out_look_alikes():
    assert not set("01IO") & set(referrals.ALPHABET)


def test_a_code_is_given_on_first_need_to_accounts_made_without_one(make_user):
    user = make_user(email="old@example.com")
    assert user.referral_code is None
    code = referrals.ensure_code(user)
    assert code and referrals.ensure_code(user) == code


def test_a_code_finds_an_active_member_in_any_case(ada):
    code = referrals.ensure_code(ada)
    assert referrals.referrer_for_code(code.lower()) == ada
    assert (
        referrals.referrer_for_code("NOSUCH99") is None and referrals.referrer_for_code("") is None
    )


def test_a_code_of_someone_who_is_not_active_finds_nobody(make_user):
    gone = make_user(email="gone@example.com", status="suspended")
    referrals.ensure_code(gone)
    assert referrals.referrer_for_code(gone.referral_code) is None


# --- at sign up ---


def test_naming_a_member_at_sign_up_is_recorded(api_client, ada):
    user = register(api_client, kind="member", referred_by=str(ada.pk), code="")
    assert user.referral_source == "member" and user.referred_by_id == ada.pk


def test_opening_a_link_records_the_code_and_picks_the_owner(api_client, ada):
    code = referrals.ensure_code(ada)
    user = register(api_client, kind="member", code=code)
    assert user.referred_by_id == ada.pk and user.referral_code_used == code


def test_the_applicant_can_change_the_source_but_the_code_is_kept(api_client, ada):
    code = referrals.ensure_code(ada)
    user = register(api_client, kind="social", detail="LinkedIn", code=code)
    assert user.referral_source == "social" and user.referral_detail == "LinkedIn"
    assert user.referred_by_id is None and user.referral_code_used == code


def test_a_member_who_could_not_be_found_can_be_named_in_words(api_client):
    user = register(api_client, kind="member", detail="Someone from Kuda Foods")
    assert user.referred_by_id is None and user.referral_detail == "Someone from Kuda Foods"


def test_other_sources_take_a_short_detail_but_search_and_newsletter_do_not(api_client):
    user = register(api_client, kind="search", detail="ignored")
    assert user.referral_source == "search" and user.referral_detail == ""


def test_markup_in_the_detail_is_removed(api_client):
    user = register(api_client, kind="event", detail="<b>Demo Day</b><script>x</script>")
    assert user.referral_detail == "Demo Day"


def test_saying_nothing_is_fine(api_client):
    user = register(api_client)
    assert user.referral_source == "" and user.referred_by_id is None


@pytest.mark.parametrize(
    "referral",
    [
        {"kind": "friend"},
        {"detail": "x" * 201},
        {"extra": 1},
    ],
)
def test_a_malformed_entry_is_refused(api_client, referral):
    response = api_client.post(REGISTER_URL, registration_payload(referral=referral), format="json")
    assert (
        response.status_code == 400
        and not User.objects.filter(email="new.member@example.com").exists()
    )


def test_naming_a_member_under_another_source_is_dropped_not_refused(api_client, ada):
    user = register(api_client, kind="social", detail="LinkedIn", referred_by=str(ada.pk))
    assert user.referral_source == "social" and user.referred_by_id is None


def test_a_member_who_has_left_does_not_block_the_registration(api_client, make_user):
    gone = make_user(email="gone@example.com", status="removed")
    user = register(api_client, kind="member", referred_by=str(gone.pk))
    assert user.referral_source == "member" and user.referred_by_id is None


def test_nobody_can_refer_themselves(ada):
    with pytest.raises(Exception) as caught:
        referrals.clean({"kind": "member", "referred_by": ada.pk}, own_id=ada.pk)
    assert "yourself" in str(caught.value)


# --- finding a member to name ---


def test_a_newcomer_finds_members_by_name(api_client, ada, make_user):
    member(make_user, "tunde@example.com", "Tunde Bakare")
    found = api_client.get(SEARCH, {"q": "adaez"}).json()["results"]
    assert [r["name"] for r in found] == ["Adaeze Okafor"]
    assert set(found[0]) == {"id", "name", "headline", "photo", "startup"}


def test_an_email_finds_someone_only_when_typed_in_full(api_client, ada):
    assert [
        r["id"] for r in api_client.get(SEARCH, {"q": "ada@example.com"}).json()["results"]
    ] == [str(ada.pk)]
    assert api_client.get(SEARCH, {"q": "ada@exam"}).json()["results"] == []


def test_people_who_keep_their_name_from_visitors_are_not_offered(api_client, make_user):
    member(make_user, "hidden@example.com", "Hidden Person", public=False)
    assert api_client.get(SEARCH, {"q": "Hidden"}).json()["results"] == []


def test_pending_and_suspended_people_are_not_offered(api_client, make_user):
    waiting = member(make_user, "wait@example.com", "Waiting Person")
    waiting.status = "pending"
    waiting.save(update_fields=["status"])
    assert api_client.get(SEARCH, {"q": "Waiting"}).json()["results"] == []


def test_a_short_query_finds_nothing_and_a_huge_one_is_refused(api_client, ada):
    assert api_client.get(SEARCH, {"q": "ad"}).json()["results"] == []
    assert api_client.get(SEARCH, {"q": "x" * 101}).status_code == 400
    assert api_client.get(SEARCH).status_code == 400


def test_at_most_five_come_back(api_client, make_user):
    for n in range(8):
        member(make_user, f"p{n}@example.com", f"Pat Person {n}")
    assert len(api_client.get(SEARCH, {"q": "Pat"}).json()["results"]) == 5


def test_the_search_is_throttled_by_address(api_client, ada, monkeypatch):
    monkeypatch.setattr(ScopedRateThrottle, "THROTTLE_RATES", {"referrer_search": "3/hour"})
    codes = [api_client.get(SEARCH, {"q": "Adaeze"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# --- a member's own referrals ---


def test_a_member_sees_their_code_link_and_who_joined(ada, client_for, make_user):
    joined = member(make_user, "joined@example.com", "Joined Person")
    joined.referred_by = ada
    joined.save(update_fields=["referred_by"])
    waiting = make_user(email="waiting@example.com", status="pending")
    waiting.referred_by = ada
    waiting.save(update_fields=["referred_by"])
    body = client_for(ada).get(MINE).json()
    assert len(body["code"]) == 8 and body["url"].endswith(f"/join?ref={body['code']}")
    assert body["approved_count"] == 1 and body["waiting_count"] == 1
    assert [m["name"] for m in body["members"]] == ["Joined Person"]


def test_a_referred_member_who_hides_their_name_shows_as_a_community_member(
    ada, client_for, make_user
):
    hidden = member(make_user, "h@example.com", "Secret Name", public=False)
    FounderProfile.objects.filter(user=hidden).update(visibility={"basics": "private"})
    hidden.referred_by = ada
    hidden.save(update_fields=["referred_by"])
    names = [m["name"] for m in client_for(ada).get(MINE).json()["members"]]
    assert names == ["Community member"]


def test_the_list_is_only_yours(ada, client_for, make_user):
    other = member(make_user, "other@example.com", "Other Member")
    assert client_for(other).get(MINE).json()["members"] == []


def test_my_referrals_need_an_active_member(api_client, make_user, client_for):
    assert api_client.get(MINE).status_code == 401
    pending = make_user(roles=(), status="pending", email="p@example.com")
    assert client_for(pending).get(MINE).status_code == 403


# --- the console ---


def test_the_summary_compares_this_month_with_last_and_breaks_down_sources(admin, ada, make_user):
    a = make_user(email="a@example.com", referral_source="member")
    b = make_user(email="b@example.com", referral_source="social")
    c = make_user(email="c@example.com")
    User.objects.filter(pk=a.pk).update(referred_by=ada)
    body = admin.get(SUMMARY).json()
    assert body["this_month"]["referred"] == 1 and body["this_month"]["signups"] >= 4
    assert body["last_month"] == {"signups": 0, "referred": 0, "approved": 0}
    kinds = {s["kind"]: s["count"] for s in body["sources"]}
    assert kinds["member"] == 1 and kinds["social"] == 1 and kinds["none"] >= 2
    assert body["referred_share"] == round(100 * 1 / body["this_month"]["signups"]) and b and c


def test_last_months_sign_ups_are_counted_separately(admin, ada, make_user):
    old = make_user(email="old2@example.com")
    when = timezone.now().replace(day=1) - timezone.timedelta(days=3)
    User.objects.filter(pk=old.pk).update(created_at=when, referred_by=ada)
    last = admin.get(SUMMARY).json()["last_month"]
    assert last["signups"] == 1 and last["referred"] == 1


def test_top_referrers_counts_only_approved_referrals(admin, ada, make_user):
    tunde = member(make_user, "tunde@example.com", "Tunde Bakare")
    for n in range(3):
        User.objects.filter(pk=member(make_user, f"j{n}@example.com").pk).update(referred_by=ada)
    User.objects.filter(pk=member(make_user, "k@example.com").pk).update(referred_by=tunde)
    pending = make_user(email="pend@example.com", status="pending")
    User.objects.filter(pk=pending.pk).update(referred_by=tunde)
    top = admin.get(TOP).json()
    assert [(t["name"], t["approved"]) for t in top] == [("Adaeze Okafor", 3), ("Tunde Bakare", 1)]
    assert len(admin.get(TOP, {"limit": 1}).json()) == 1
    assert admin.get(TOP, {"limit": 99}).status_code == 400


def test_the_members_table_shows_and_filters_by_source_and_referrer(admin, ada, make_user):
    kept = make_user(email="kept@example.com", referral_source="member")
    User.objects.filter(pk=kept.pk).update(referred_by=ada)
    make_user(email="plain@example.com")
    rows = admin.get("/api/v1/admin/members", {"referred_by": str(ada.pk)}).json()["results"]
    assert [r["email"] for r in rows] == ["kept@example.com"]
    assert rows[0]["referrer"] == {"id": str(ada.pk), "name": "Adaeze Okafor"}
    assert rows[0]["referral_label"] == "A WO Community member"
    by_source = admin.get("/api/v1/admin/members", {"referral_source": "member"}).json()["results"]
    assert [r["email"] for r in by_source] == ["kept@example.com"]
    none = admin.get("/api/v1/admin/members", {"referral_source": "none"}).json()["results"]
    assert "kept@example.com" not in [r["email"] for r in none]
    assert admin.get("/api/v1/admin/members", {"referral_source": "bogus"}).status_code == 400


def test_the_application_shows_how_someone_heard_of_us(admin, ada, make_user):
    code = referrals.ensure_code(ada)
    person = make_user(email="newbie@example.com", status="pending")
    User.objects.filter(pk=person.pk).update(
        referral_source="member", referred_by=ada, referral_code_used=code
    )
    body = admin.get(f"/api/v1/admin/members/{person.pk}/application").json()["referral"]
    assert body["kind"] == "member" and body["kind_label"] == "A WO Community member"
    assert body["referrer"]["name"] == "Adaeze Okafor" and body["code_used"] == code


def test_an_admin_can_correct_a_referral_and_it_is_audited(admin, ada, make_user):
    person = make_user(email="newbie@example.com", status="pending")
    url = f"/api/v1/admin/members/{person.pk}/referral"
    done = admin.patch(url, {"kind": "member", "referred_by": str(ada.pk)}, format="json")
    assert done.status_code == 200 and done.json()["referrer"]["name"] == "Adaeze Okafor"
    again = admin.patch(url, {"kind": "event", "detail": "Demo Day"}, format="json").json()
    assert again["kind"] == "event" and again["detail"] == "Demo Day" and again["referrer"] is None
    assert AuditLog.objects.filter(action="member.referral_edited").count() == 2


def test_an_admin_cannot_make_someone_their_own_referrer(admin, make_user):
    person = member(make_user, "self@example.com", "Self Person")
    refused = admin.patch(
        f"/api/v1/admin/members/{person.pk}/referral",
        {"kind": "member", "referred_by": str(person.pk)},
        format="json",
    )
    assert refused.status_code == 400


@pytest.mark.parametrize(
    "payload", [{"kind": "friend"}, {"detail": "x" * 201}, {"referred_by": "nope"}, {"x": 1}]
)
def test_bad_corrections_are_refused(admin, make_user, payload):
    person = make_user(email="newbie@example.com", status="pending")
    assert (
        admin.patch(
            f"/api/v1/admin/members/{person.pk}/referral", payload, format="json"
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", SUMMARY, None),
        ("get", TOP, None),
        (
            "patch",
            "/api/v1/admin/members/00000000-0000-0000-0000-000000000001/referral",
            {"kind": "social"},
        ),
    ],
)
def test_the_console_endpoints_need_the_right_role(
    api_client, ada, client_for, method, path, payload
):
    def call(c):
        send = getattr(c, method)
        return send(path, payload, format="json") if payload else send(path)

    assert call(api_client).status_code == 401
    assert call(client_for(ada, mfa_age=5)).status_code == 403
    assert call(client_for(ada)).status_code == 403


def test_the_admin_endpoints_need_the_second_step(make_user, client_for):
    boss = make_user(roles=("community_admin",), email="boss@example.com")
    assert client_for(boss).get(SUMMARY).status_code == 403


def test_the_selectors_agree_with_the_endpoints(ada):
    assert selectors.search_referrers("ad") == []
    assert selectors.link_for("ABC").endswith("/join?ref=ABC")


def test_capturing_a_source_is_counted_in_analytics(api_client, ada):
    from apps.analytics.models import AnalyticsEvent

    register(api_client, kind="event", detail="Demo Day")
    event = AnalyticsEvent.objects.get(name="referral_captured")
    assert event.properties == {"kind": "event"}


# --- who a link belongs to ---

BY_CODE = "/api/v1/members/referrer-by-code"


def test_a_link_says_who_it_came_from(api_client, ada):
    code = referrals.ensure_code(ada)
    body = api_client.get(BY_CODE, {"code": code.lower()}).json()
    assert body["found"] is True and body["id"] == str(ada.pk) and body["name"] == "Adaeze Okafor"


def test_an_unknown_code_is_not_found(api_client):
    body = api_client.get(BY_CODE, {"code": "NOSUCH99"}).json()
    assert body == {"found": False, "id": None, "name": "", "startup": "", "photo": None}


def test_a_private_member_is_found_without_a_name(api_client, make_user):
    private = member(make_user, "priv@example.com", "Private Person", public=False)
    body = api_client.get(BY_CODE, {"code": referrals.ensure_code(private)}).json()
    assert body["found"] is True and body["id"] is None and body["name"] == "A WO Community member"


def test_a_suspended_members_code_is_not_found(api_client, make_user):
    gone = make_user(email="gone2@example.com", status="suspended")
    assert api_client.get(BY_CODE, {"code": referrals.ensure_code(gone)}).json()["found"] is False


@pytest.mark.parametrize("params", [{}, {"code": ""}, {"code": "X" * 13}, {"code": "ABC", "x": 1}])
def test_a_bad_lookup_is_refused(api_client, params):
    assert api_client.get(BY_CODE, params).status_code == 400
