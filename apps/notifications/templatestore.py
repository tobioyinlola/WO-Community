"""Edited wording for email templates: read, save with history, restore and reset."""

from typing import Any

from django.db import transaction
from rest_framework import exceptions

from apps.audit import services as audit
from apps.notifications import mailtemplates as mt
from apps.notifications.models import EmailTemplate, EmailTemplateVersion


def effective_copy(key: str) -> mt.Copy:
    """The wording to send: the edited one if there is one, else the built-in."""
    row = EmailTemplate.objects.filter(key=key).first()
    if row is None:
        return mt.default_copy(mt.TEMPLATES[key])
    return mt.Copy(row.subject, row.preheader, row.body)


def _tpl(key: str) -> mt.TemplateDef:
    tpl = mt.TEMPLATES.get(key)
    if tpl is None:
        raise exceptions.NotFound()
    return tpl


def describe(key: str) -> dict[str, Any]:
    tpl = _tpl(key)
    row = EmailTemplate.objects.filter(key=key).first()
    copy = mt.Copy(row.subject, row.preheader, row.body) if row else mt.default_copy(tpl)
    default = mt.default_copy(tpl)
    return {
        "key": key,
        "name": tpl.name,
        "about": tpl.about,
        "stream": tpl.stream,
        "subject": copy.subject,
        "preheader": copy.preheader,
        "body": copy.body,
        "edited": row is not None,
        "version": row.version if row else 0,
        "updated_at": row.updated_at if row else None,
        "default_subject": default.subject,
        "default_preheader": default.preheader,
        "default_body": default.body,
        "variables": [
            {
                "name": v.name,
                "kind": v.kind,
                "required": v.required,
                "must_appear": v.must_appear,
                "sample": v.sample,
            }
            for v in tpl.variables
        ],
    }


def list_all() -> list[dict[str, Any]]:
    edited = {r.key: r for r in EmailTemplate.objects.all()}
    out = []
    for key, tpl in mt.TEMPLATES.items():
        row = edited.get(key)
        out.append(
            {
                "key": key,
                "name": tpl.name,
                "about": tpl.about,
                "stream": tpl.stream,
                "subject": row.subject if row else tpl.subject,
                "edited": row is not None,
                "version": row.version if row else 0,
                "updated_at": row.updated_at if row else None,
            }
        )
    return out


def _validated(key: str, subject: str, preheader: str, body: str) -> tuple[str, str, str]:
    tpl = _tpl(key)
    subject = " ".join(subject.split())
    preheader = " ".join(preheader.split())
    body = body.replace("\r\n", "\n").strip()
    try:
        mt.check_copy(tpl, subject, preheader, body)
        # Render with the sample data too, so a copy that cannot be built is refused now.
        mt.render(key, tpl.sample(), copy=mt.Copy(subject, preheader, body))
    except mt.TemplateError as exc:
        raise exceptions.ValidationError({"body": [str(exc)]}) from exc
    return subject, preheader, body


def _write(
    actor: Any, key: str, subject: str, preheader: str, body: str, note: str, ip: str
) -> EmailTemplate:
    with transaction.atomic():
        row = EmailTemplate.objects.select_for_update().filter(key=key).first()
        before = (
            {"subject": row.subject, "preheader": row.preheader, "body": row.body}
            if row
            else {
                "subject": _tpl(key).subject,
                "preheader": _tpl(key).preheader,
                "body": _tpl(key).body,
            }
        )
        if row is None:
            # Keep the built-in wording as version 1, so it can always be put back.
            default = mt.default_copy(_tpl(key))
            EmailTemplateVersion.objects.get_or_create(
                template_key=key,
                version=1,
                defaults={
                    "subject": default.subject,
                    "preheader": default.preheader,
                    "body": default.body,
                    "note": "Built in wording",
                },
            )
            row = EmailTemplate(key=key, version=1)
        row.version += 1
        row.subject, row.preheader, row.body, row.updated_by = subject, preheader, body, actor
        row.save()
        EmailTemplateVersion.objects.create(
            template_key=key,
            version=row.version,
            subject=subject,
            preheader=preheader,
            body=body,
            saved_by=actor,
            note=note[:120],
        )
        audit.record(
            actor=actor,
            action="email.template_edited",
            target_type="email_template",
            target_id=key,
            target_label=_tpl(key).name,
            before=before,
            after={
                "subject": subject,
                "preheader": preheader,
                "body": body,
                "version": row.version,
            },
            ip=ip,
        )
        return row


def save(
    *, actor: Any, key: str, subject: str, preheader: str, body: str, note: str = "", ip: str = ""
) -> EmailTemplate:
    subject, preheader, body = _validated(key, subject, preheader, body)
    return _write(actor, key, subject, preheader, body, note, ip)


def versions(key: str) -> list[EmailTemplateVersion]:
    _tpl(key)
    return list(EmailTemplateVersion.objects.filter(template_key=key).order_by("-version")[:50])


def restore(*, actor: Any, key: str, version: int, ip: str = "") -> EmailTemplate:
    found = EmailTemplateVersion.objects.filter(template_key=key, version=version).first()
    if found is None:
        raise exceptions.NotFound()
    subject, preheader, body = _validated(key, found.subject, found.preheader, found.body)
    return _write(actor, key, subject, preheader, body, f"Restored version {version}", ip)


def reset(*, actor: Any, key: str, ip: str = "") -> None:
    """Go back to the built-in wording. The history is kept."""
    tpl = _tpl(key)
    with transaction.atomic():
        row = EmailTemplate.objects.select_for_update().filter(key=key).first()
        if row is None:
            return
        audit.record(
            actor=actor,
            action="email.template_reset",
            target_type="email_template",
            target_id=key,
            target_label=tpl.name,
            before={"subject": row.subject, "preheader": row.preheader, "body": row.body},
            ip=ip,
        )
        row.delete()
