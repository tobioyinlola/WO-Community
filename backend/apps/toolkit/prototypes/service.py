"""Prototypes: a specification made from a template or from the venture, edited by patch.

A prototype is data the front end draws; there is no code in it. A model may draft one from the
profile, but whatever it returns is validated against the registry and limits before it is saved,
and if it cannot be made valid the founder gets a template instead of an error.
"""

import copy
from typing import Any
from uuid import UUID

import structlog
from django.conf import settings
from django.db import transaction
from rest_framework import exceptions

from apps.core import jsonpatch
from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.toolkit.ai import runner, safety
from apps.toolkit.jobs.services import JobContext, JobFailed
from apps.toolkit.prototypes import registry, spec, templates
from apps.toolkit.prototypes.models import Prototype, PrototypeTemplate, PrototypeVersion
from apps.toolkit.ventures.models import Venture
from apps.toolkit.ventures.selectors import profile_of

logger = structlog.get_logger(__name__)

MAX_PROTOTYPES = 20
ROOTS = ("screens", "theme", "start", "kind")


def ensure_templates() -> None:
    have = set(PrototypeTemplate.objects.values_list("slug", flat=True))
    PrototypeTemplate.objects.bulk_create(
        PrototypeTemplate(position=i, **row)
        for i, row in enumerate(templates.TEMPLATES)
        if row["slug"] not in have
    )


def available_templates() -> list[PrototypeTemplate]:
    ensure_templates()
    return list(PrototypeTemplate.objects.filter(active=True))


def _name_in(value: Any, name: str) -> Any:
    if isinstance(value, str):
        return value.replace("{name}", name)
    if isinstance(value, list):
        return [_name_in(v, name) for v in value]
    if isinstance(value, dict):
        return {k: _name_in(v, name) for k, v in value.items()}
    return value


def _checked(raw: Any) -> dict[str, Any]:
    try:
        return spec.clean(raw)
    except spec.InvalidSpec as exc:
        raise exceptions.ValidationError({exc.path: [exc.message]}) from exc


def _snapshot(prototype: Prototype, label: str = "") -> None:
    PrototypeVersion.objects.update_or_create(
        prototype=prototype,
        version=prototype.version,
        defaults={"spec": prototype.spec, "label": label[:80]},
    )
    old = prototype.versions.order_by("-version").values_list("pk", flat=True)[
        settings.DECK_VERSIONS_KEPT :
    ]
    PrototypeVersion.objects.filter(pk__in=list(old)).delete()


def get(venture: Venture, prototype_id: UUID) -> Prototype | None:
    return Prototype.objects.filter(pk=prototype_id, venture=venture).first()


def create_from_template(venture: Venture, *, slug: str, title: str = "") -> Prototype:
    ensure_templates()
    template = PrototypeTemplate.objects.filter(slug=slug, active=True).first()
    if template is None:
        raise exceptions.ValidationError({"template": ["Choose one of the templates."]})
    if Prototype.objects.filter(venture=venture).count() >= MAX_PROTOTYPES:
        raise ConflictError(f"A venture can have {MAX_PROTOTYPES} prototypes.", code="limit")
    name = str(profile_of(venture).fields.get("name") or venture.name)
    built = _checked(_name_in(copy.deepcopy(template.spec), name))
    with transaction.atomic():
        prototype = Prototype.objects.create(
            venture=venture,
            title=plain(title or f"{name}: {template.name}")[:120],
            template_slug=template.slug,
            spec=built,
        )
        _snapshot(prototype, "Created")
    return prototype


def apply_ops(prototype: Prototype, *, ops: Any, base_version: int, label: str = "") -> Prototype:
    with transaction.atomic():
        locked = Prototype.objects.select_for_update().get(pk=prototype.pk)
        if locked.version != base_version:
            raise ConflictError(
                "The prototype changed elsewhere. Reload and try again.", code="stale"
            )
        try:
            changed = jsonpatch.apply(locked.spec, ops, roots=ROOTS)
        except jsonpatch.PatchError as exc:
            raise exceptions.ValidationError({"ops": [exc.message]}) from exc
        locked.spec = _checked(changed)
        locked.version += 1
        locked.save()
        _snapshot(locked, label)
    return locked


def rename(prototype: Prototype, title: str) -> Prototype:
    cleaned = plain(title).strip()
    if not 1 <= len(cleaned) <= 120:
        raise exceptions.ValidationError({"title": ["Between 1 and 120 characters."]})
    prototype.title = cleaned
    prototype.save()
    return prototype


def restore(prototype: Prototype, version: int) -> Prototype:
    row = prototype.versions.filter(version=version).first()
    if row is None:
        raise exceptions.NotFound()
    with transaction.atomic():
        locked = Prototype.objects.select_for_update().get(pk=prototype.pk)
        _snapshot(locked, f"Before restoring version {version}")
        locked.spec = _checked(row.spec)
        locked.version += 1
        locked.save()
        _snapshot(locked, f"Restored version {version}")
    return locked


def duplicate(prototype: Prototype) -> Prototype:
    if Prototype.objects.filter(venture=prototype.venture).count() >= MAX_PROTOTYPES:
        raise ConflictError(f"A venture can have {MAX_PROTOTYPES} prototypes.", code="limit")
    # Ids are only unique inside one prototype, so a copy keeps them.
    copy_ = Prototype.objects.create(
        venture=prototype.venture,
        title=f"{prototype.title} (copy)"[:120],
        template_slug=prototype.template_slug,
        spec=copy.deepcopy(prototype.spec),
    )
    _snapshot(copy_, "Copied")
    return copy_


# --- drafting from the venture ----------------------------------------------------------------


def _registry_summary() -> list[dict[str, Any]]:
    return [
        {
            "name": c["name"],
            "children": c["children"],
            "action": c["action"],
            "props": {
                k: (v.get("values") or v["kind"]) if v["kind"] == "enum" else v["kind"]
                for k, v in c["props"].items()
            },
        }
        for c in registry.catalogue()
    ]


def generate(ctx: JobContext) -> dict[str, Any]:
    """The ``prototype.generate`` job. Payload: ``brief``, ``kind`` and ``title``."""
    venture = ctx.venture
    if venture is None:
        raise JobFailed("no_venture", "This job needs a venture.")
    fields = profile_of(venture).fields
    brief = plain(str(ctx.payload.get("brief", "")))[:500]
    kind = str(ctx.payload.get("kind", "web"))
    if kind not in spec.KINDS:
        raise JobFailed("bad_kind", "Choose web or mobile.")
    ctx.progress(10, "Reading your profile")
    notes = ""
    drafted: dict[str, Any] | None = None
    for attempt in (1, 2):
        answer = runner.structured(
            prompt_id="prototype.generate",
            variables={
                "venture": {
                    "name": fields.get("name", venture.name),
                    "one_liner": fields.get("one_liner", ""),
                    "problem": fields.get("problem", ""),
                    "solution": fields.get("solution", ""),
                    "features": fields.get("key_features", []),
                    "customer_type": fields.get("customer_type", ""),
                },
                "brief": brief or "none",
                "kind": kind,
                "components": _registry_summary(),
                "notes": notes or "none",
            },
            owner_id=ctx.owner_id,
            venture=venture,
            job=ctx.job,
        )
        ctx.progress(40 + 30 * attempt, "Checking the design")
        try:
            drafted = spec.clean({**answer, "kind": answer.get("kind", kind)})
            break
        except spec.InvalidSpec as exc:
            notes = f"The last answer was refused: {exc.path}: {exc.message}"
            logger.info("prototype_draft_refused", attempt=attempt, path=exc.path)
    title = plain(str(ctx.payload.get("title", "")))[:120] or f"{venture.name}: prototype"
    if drafted is None:
        # The model could not produce a valid design twice: start from a template instead.
        fallback = "marketplace" if kind == "mobile" else "landing"
        made = create_from_template(venture, slug=fallback, title=title)
        return {"type": "prototype", "id": str(made.pk), "fallback": True}
    with transaction.atomic():
        prototype = Prototype.objects.create(venture=venture, title=title, spec=drafted)
        _snapshot(prototype, "Drafted")
    return {"type": "prototype", "id": str(prototype.pk), "fallback": False}


def check_brief(brief: str) -> str:
    cleaned = plain(brief).strip()
    if len(cleaned) > 500:
        raise exceptions.ValidationError({"brief": ["At most 500 characters."]})
    screened = safety.screen(cleaned) if cleaned else None
    if screened is not None and screened.blocked:
        raise exceptions.ValidationError({"brief": [screened.reply]})
    return cleaned
