import pytest

from apps.toolkit.ai.providers.fake import FakeLLMProvider
from apps.toolkit.prototypes import registry, spec, templates
from apps.toolkit.prototypes.models import Prototype
from apps.toolkit.testing import BASE

pytestmark = pytest.mark.django_db


def url(venture, tail=""):
    return f"{BASE}/ventures/{venture['id']}/prototypes{tail}"


def make(client, venture, template="landing"):
    response = client.post(url(venture), {"template": template}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def patch(client, venture, proto, ops):
    return client.patch(
        url(venture, f"/{proto['id']}"),
        {"base_version": proto["version"], "ops": ops},
        format="json",
    )


def test_the_registry_has_at_least_forty_components_with_rules():
    assert len(registry.COMPONENTS) >= 40
    assert {c["category"] for c in registry.COMPONENTS.values()} >= {
        "layout",
        "text",
        "input",
        "action",
        "data",
        "navigation",
        "feedback",
    }


def test_every_template_is_valid_against_the_registry():
    assert len(templates.TEMPLATES) >= 8
    for template in templates.TEMPLATES:
        cleaned = spec.clean(template["spec"])
        assert cleaned["screens"], template["slug"]


def test_components_and_templates_are_listed(client):
    components = client.get(f"{BASE}/prototype-components").json()
    assert len(components) >= 40 and {"name", "props", "children", "action"} <= set(components[0])
    listed = client.get(f"{BASE}/prototype-templates").json()
    assert len(listed) >= 8 and {t["kind"] for t in listed} == {"web", "mobile"}


def test_a_prototype_is_made_from_a_template_with_the_ventures_name(client, full_venture):
    proto = make(client, full_venture)
    assert proto["version"] == 1 and proto["spec"]["start"] == "home"
    assert "Mamapesa" in str(proto["spec"]) and "{name}" not in str(proto["spec"])
    assert client.post(url(full_venture), {"template": "nope"}, format="json").status_code == 400


def test_patching_adds_components_and_navigation(client, full_venture):
    proto = make(client, full_venture, "booking")
    ok = patch(
        client,
        full_venture,
        proto,
        [
            {
                "op": "add",
                "path": "/screens/0/root/children/-",
                "value": {
                    "component": "button",
                    "props": {"text": "<b>Help</b>"},
                    "action": {"type": "navigate", "screen": "confirmed"},
                },
            }
        ],
    )
    assert ok.status_code == 200, ok.content
    button = ok.json()["spec"]["screens"][0]["root"]["children"][-1]
    assert button["props"]["text"] == "Help" and button["action"]["screen"] == "confirmed"


@pytest.mark.parametrize(
    ("value", "needle"),
    [
        ({"component": "iframe", "props": {}}, "component"),
        ({"component": "button", "props": {"onclick": "x()"}}, "props"),
        ({"component": "text", "props": {"text": "x" * 401}}, "props"),
        ({"component": "text", "props": {"tone": "purple"}}, "props"),
        ({"component": "text", "children": [{"component": "text"}]}, "children"),
        ({"component": "text", "action": {"type": "navigate", "screen": "home"}}, "action"),
        ({"component": "button", "action": {"type": "navigate", "screen": "ghost"}}, "action"),
        (
            {"component": "button", "action": {"type": "open_url", "url": "https://x.example"}},
            "action",
        ),
    ],
)
def test_bad_components_are_refused_by_name(client, full_venture, value, needle):
    proto = make(client, full_venture, "booking")
    response = patch(
        client,
        full_venture,
        proto,
        [{"op": "add", "path": "/screens/0/root/children/-", "value": value}],
    )
    assert response.status_code == 400
    assert needle in str(response.json())
    assert client.get(url(full_venture, f"/{proto['id']}")).json()["version"] == 1


def test_depth_and_screen_limits(client, full_venture, settings):
    proto = make(client, full_venture, "settings")
    node = {"component": "text", "props": {"text": "deep"}}
    for _ in range(9):
        node = {"component": "container", "children": [node]}
    deep = patch(
        client,
        full_venture,
        proto,
        [{"op": "add", "path": "/screens/0/root/children/-", "value": node}],
    )
    assert deep.status_code == 400 and "levels" in str(deep.json())

    settings.PROTOTYPE_MAX_SCREENS = 1
    more = patch(
        client,
        full_venture,
        proto,
        [
            {
                "op": "add",
                "path": "/screens/-",
                "value": {"name": "Two", "root": {"component": "container"}},
            }
        ],
    )
    assert more.status_code == 400


def test_a_stale_version_is_a_conflict(client, full_venture):
    proto = make(client, full_venture)
    ops = [{"op": "replace", "path": "/theme", "value": {"palette": "dark", "font": "serif"}}]
    assert patch(client, full_venture, proto, ops).status_code == 200
    assert patch(client, full_venture, proto, ops).status_code == 409


def test_drafting_from_the_profile_validates_what_the_model_returns(client, full_venture, run_jobs):
    FakeLLMProvider.canned["prototype.generate"] = {
        "title": "Traders app",
        "kind": "mobile",
        "start": "home",
        "screens": [
            {
                "id": "home",
                "name": "Home",
                "root": {
                    "component": "container",
                    "children": [
                        {"component": "heading", "props": {"text": "Mamapesa", "level": 1}},
                        {
                            "component": "button",
                            "props": {"text": "Get a loan"},
                            "action": {"type": "navigate", "screen": "loan"},
                        },
                    ],
                },
            },
            {
                "id": "loan",
                "name": "Loan",
                "root": {
                    "component": "container",
                    "children": [
                        {"component": "slider", "props": {"label": "Amount", "min": 0, "max": 100}}
                    ],
                },
            },
        ],
    }
    started = client.post(url(full_venture, "/generate"), {"kind": "mobile"}, format="json")
    assert started.status_code == 202, started.content
    run_jobs()
    job = client.get(f"{BASE}/jobs/{started.json()['id']}").json()
    assert job["status"] == "succeeded" and job["result"]["fallback"] is False
    made = client.get(url(full_venture, f"/{job['result']['id']}")).json()
    assert [s["name"] for s in made["spec"]["screens"]] == ["Home", "Loan"]


def test_an_unusable_draft_falls_back_to_a_template(client, full_venture, run_jobs):
    FakeLLMProvider.canned["prototype.generate"] = {
        "title": "Bad",
        "kind": "web",
        "screens": [{"id": "a", "name": "A", "root": {"component": "script", "props": {}}}],
    }
    started = client.post(url(full_venture, "/generate"), {"kind": "web"}, format="json")
    run_jobs()
    job = client.get(f"{BASE}/jobs/{started.json()['id']}").json()
    assert job["status"] == "succeeded" and job["result"]["fallback"] is True
    assert Prototype.objects.get().template_slug == "landing"
    tries = [c for c in FakeLLMProvider.calls if c.prompt_id == "prototype.generate"]
    assert len(tries) == 2 and "refused" in tries[1].variables["notes"]


def test_a_brief_asking_for_made_up_proof_is_declined(client, full_venture):
    response = client.post(
        url(full_venture, "/generate"),
        {"brief": "Show fake customers and inflated traction numbers on the home screen"},
        format="json",
    )
    assert response.status_code == 400 and "brief" in str(response.json())


def test_copy_versions_and_restore(client, full_venture):
    proto = make(client, full_venture, "settings")
    changed = patch(
        client,
        full_venture,
        proto,
        [{"op": "replace", "path": "/theme", "value": {"palette": "warm", "font": "sans"}}],
    ).json()
    assert changed["spec"]["theme"]["palette"] == "warm"
    restored = client.post(url(full_venture, f"/{proto['id']}/versions/1/restore")).json()
    assert restored["spec"]["theme"]["palette"] == "light" and restored["version"] == 3
    copy = client.post(url(full_venture, f"/{proto['id']}/duplicate")).json()
    assert copy["title"].endswith("(copy)") and copy["id"] != proto["id"]
    assert len(client.get(url(full_venture)).json()) == 2


def test_a_prototype_can_be_shared_read_only(client, api_client, full_venture):
    proto = make(client, full_venture)
    made = client.post(
        f"{BASE}/ventures/{full_venture['id']}/shares",
        {"subject_type": "prototype", "subject_id": proto["id"]},
        format="json",
    ).json()
    shown = api_client.get(f"{BASE}/public/share/{made['token']}")
    assert shown.status_code == 200
    assert shown.json()["type"] == "prototype" and shown.json()["spec"]["screens"]


def test_only_the_owner_reaches_a_prototype(client, other_client, api_client, full_venture):
    proto = make(client, full_venture)
    base = url(full_venture, f"/{proto['id']}")
    for tail in ("", "/versions"):
        assert other_client.get(base + tail).status_code == 404
    assert other_client.get(url(full_venture)).status_code == 404
    assert (
        other_client.post(url(full_venture), {"template": "landing"}, format="json").status_code
        == 404
    )
    assert other_client.delete(base).status_code == 404
    assert api_client.get(url(full_venture)).status_code == 401


def test_the_flag_switches_prototypes_off(client, full_venture, settings):
    settings.TOOLKIT_FEATURES = {**settings.TOOLKIT_FEATURES, "prototypes": False}
    assert client.get(url(full_venture)).status_code == 404
    assert client.get(f"{BASE}/prototype-components").status_code == 404
