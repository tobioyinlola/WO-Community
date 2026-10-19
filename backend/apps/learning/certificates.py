"""Certificates of completion: issuing, the template, the stored PDF, revoking and reissuing.

A certificate is issued by a worker when a member finishes a course. It copies what it needs (the
learner's name, the course title and length, and the template as it was) so nothing a person or an
administrator changes later alters it. The PDF is drawn once, kept in the private bucket and handed
out only through a short lived link; if it is asked for before the worker has drawn it, it is
drawn then.
"""

import io
import secrets
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from PIL import Image
from rest_framework import exceptions

from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core.errors import ConflictError
from apps.core.text import plain
from apps.integrations.storage import MEDIA, PRIVATE, get_storage
from apps.learning.models import Certificate, CertificateSettings, Enrolment
from apps.learning.pdf import CertificateContent, render_certificate
from apps.notifications import notify
from apps.profiles import selectors as profiles
from apps.uploads import services as uploads

logger = structlog.get_logger(__name__)

PDF_TYPE = "application/pdf"
DEFAULT_TITLE = "Certificate of completion"
NAME_FALLBACK = "WO Community member"


# --- the template ---


def current_settings() -> CertificateSettings:
    """The one settings row, made on first use."""
    row = CertificateSettings.objects.order_by("created_at").first()
    return row or CertificateSettings.objects.create()


def snapshot_of(row: CertificateSettings) -> dict[str, Any]:
    return {
        "title_text": row.title_text,
        "signatory_name": row.signatory_name,
        "signatory_title": row.signatory_title,
        "signature_key": row.signature_key,
        "version": row.version,
    }


def update_settings(*, actor: Any, data: dict[str, Any], ip: str = "") -> CertificateSettings:
    """Change the template. New certificates use it; issued ones keep what they were drawn with."""
    with transaction.atomic():
        row = CertificateSettings.objects.select_for_update().order_by("created_at").first()
        row = row or CertificateSettings.objects.create()
        before = snapshot_of(row)
        for field in ("title_text", "signatory_name", "signatory_title"):
            if field in data:
                clean = plain(data[field])
                if field == "title_text" and not clean:
                    raise exceptions.ValidationError({field: ["This field may not be blank."]})
                setattr(row, field, clean)
        previous_key = row.signature_key
        if data.get("remove_signature"):
            row.signature_key = ""
        if data.get("signature_upload_id"):
            upload = uploads.claim(
                upload_id=data["signature_upload_id"],
                owner_id=actor.pk,
                purpose="cert_signature",
            )
            row.signature_key = upload.base_key
        row.version += 1
        row.updated_by = actor
        row.save()
        if previous_key and previous_key != row.signature_key:
            # Issued certificates keep a PDF of their own, but a reissue reads the key from its own
            # snapshot, so the old image is released only once no snapshot can need it.
            if not Certificate.objects.filter(template__signature_key=previous_key).exists():
                uploads.release(previous_key)
        audit.record(
            actor=actor,
            action="certificates.template_changed",
            target_type="certificate_settings",
            target_id=row.pk,
            before=before,
            after=snapshot_of(row),
            ip=ip,
        )
    return row


def signature_url(key: str) -> str | None:
    urls = uploads.image_urls(key)
    return urls["large"] if urls else None


def _signature_png(key: str) -> bytes | None:
    """The signature as a PNG for the PDF, or None if there is none or it cannot be read."""
    if not key:
        return None
    try:
        raw = get_storage().read(bucket=MEDIA, key=f"{key}/large.webp", max_size=2_000_000)
        out = io.BytesIO()
        Image.open(io.BytesIO(raw)).convert("RGBA").save(out, "PNG")
        return out.getvalue()
    except Exception:  # a missing signature must not stop a certificate being issued
        logger.warning("certificate_signature_unreadable", key=key)
        return None


# --- drawing ---


def verify_url_for(number: str) -> str:
    return f"{settings.FRONTEND_BASE_URL}/verify/{number}"


def hours_of(seconds: int) -> Decimal:
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def content_for(certificate: Certificate) -> CertificateContent:
    template = certificate.template or {}
    row = current_settings()
    return CertificateContent(
        holder=certificate.holder_name,
        course=certificate.course_title,
        issued_at=certificate.issued_at,
        number=certificate.code,
        hours=certificate.hours,
        title_text=template.get("title_text") or DEFAULT_TITLE,
        # The name and signature on the sheet are the ones in the settings today, so a reissue or
        # a new download always carries the current signatory.
        signatory_name=row.signatory_name or template.get("signatory_name", ""),
        signature_png=_signature_png(row.signature_key),
    )


def preview_pdf(*, data: dict[str, Any]) -> bytes:
    """The template drawn with sample details and the settings being edited, saved or not."""
    row = current_settings()
    content = CertificateContent(
        holder=data.get("holder_name") or "Amaka Obi",
        course="Founder fundamentals",
        issued_at=timezone.now(),
        number="WO-C-2026-000341",
        hours=Decimal("4.5"),
        title_text=plain(data.get("title_text") or row.title_text) or DEFAULT_TITLE,
        signatory_name=plain(data.get("signatory_name", row.signatory_name)),
        signature_png=None if data.get("remove_signature") else _signature_png(row.signature_key),
    )
    return render_certificate(content)


def store_pdf(certificate: Certificate) -> bytes:
    """Draw the certificate, keep the file privately and remember where. Returns the bytes."""
    data = render_certificate(content_for(certificate))
    key = f"certificates/{certificate.pk}-{secrets.token_hex(12)}.pdf"
    storage = get_storage()
    storage.write(bucket=PRIVATE, key=key, data=data, content_type=PDF_TYPE)
    previous = certificate.pdf_key
    Certificate.objects.filter(pk=certificate.pk).update(pdf_key=key, updated_at=timezone.now())
    certificate.pdf_key = key
    if previous:
        storage.delete(bucket=PRIVATE, key=previous)
    return data


def download_link(certificate: Certificate) -> tuple[str, int, str]:
    """A short lived address for the PDF, its lifetime and file name. Draws it if needed."""
    if not certificate.is_valid:
        raise ConflictError("This certificate has been revoked.")
    if (
        not certificate.pdf_key
        or get_storage().head(bucket=PRIVATE, key=certificate.pdf_key) is None
    ):
        store_pdf(certificate)
    filename = f"certificate-{certificate.code}.pdf"
    url, ttl = uploads.document_link(
        key=certificate.pdf_key, filename=filename, content_type=PDF_TYPE
    )
    return url, ttl, filename


# --- issuing ---


def _new_number(year: int) -> str:
    return f"WO-C-{year}-{secrets.randbelow(1_000_000):06d}"


def issue(enrolment_id: UUID) -> Certificate | None:
    """Create the certificate for a completed course. Safe to run twice."""
    enrolment = (
        Enrolment.objects.select_related("course")
        .filter(pk=enrolment_id, completed_at__isnull=False)
        .first()
    )
    if enrolment is None or not enrolment.course.certificate_enabled:
        return None
    existing = Certificate.objects.filter(enrolment=enrolment).first()
    if existing is not None:
        return existing
    holder = plain(profiles.full_name_of(enrolment.user_id) or NAME_FALLBACK)[:160]
    now = timezone.now()
    template = snapshot_of(current_settings())
    for _ in range(8):  # a clash on the random number is unlikely, but handled
        try:
            with transaction.atomic():
                certificate = Certificate.objects.create(
                    enrolment=enrolment,
                    code=_new_number(now.year),
                    holder_name=holder,
                    course_title=enrolment.course.title,
                    issued_at=now,
                    hours=hours_of(enrolment.course.total_duration_seconds),
                    template=template,
                )
            break
        except IntegrityError:
            existing = Certificate.objects.filter(enrolment=enrolment).first()
            if existing is not None:
                return existing
    else:
        raise RuntimeError("could not allocate a certificate number")
    try:
        store_pdf(certificate)
    except Exception:  # the file is drawn again on first download, so this must not undo the award
        logger.exception("certificate_pdf_failed", certificate_id=str(certificate.pk))
    audit.record(
        actor=None,
        action="certificates.issued",
        target_type="certificate",
        target_id=certificate.pk,
        target_label=certificate.course_title,
        after={"number": certificate.code},
    )
    analytics.track(
        "certificate_issued",
        actor_id=enrolment.user_id,
        properties={"course_id": enrolment.course.slug},
    )
    notify.notify(
        enrolment.user_id,
        "certificate_ready",
        {"certificate_id": str(certificate.pk), "title": certificate.course_title},
        dedupe_key=f"certificate:{certificate.pk}",
    )
    return certificate


# --- administration ---


def _get(certificate_id: UUID) -> Certificate:
    certificate = (
        Certificate.objects.select_related("enrolment__course")
        .select_for_update()
        .filter(pk=certificate_id)
        .first()
    )
    if certificate is None:
        raise exceptions.NotFound()
    return certificate


def revoke(*, actor: Any, certificate_id: UUID, reason: str, ip: str = "") -> Certificate:
    """Make a certificate invalid: the public page says so and the member cannot download it."""
    clean = plain(reason)
    if not clean:
        raise exceptions.ValidationError({"reason": ["Say why it is being revoked."]})
    with transaction.atomic():
        certificate = _get(certificate_id)
        if certificate.revoked_at is not None:
            raise ConflictError("This certificate is already revoked.")
        certificate.revoked_at = timezone.now()
        certificate.revoked_reason = clean[:300]
        certificate.save(update_fields=["revoked_at", "revoked_reason", "updated_at"])
        analytics.track(
            "certificate_revoked",
            actor_id=getattr(actor, "pk", None),
            properties={"course_id": certificate.enrolment.course.slug},
        )
        audit.record(
            actor=actor,
            action="certificates.revoked",
            target_type="certificate",
            target_id=certificate.pk,
            reason=clean,
            ip=ip,
        )
    return certificate


def reissue(
    *, actor: Any, certificate_id: UUID, holder_name: str | None = None, ip: str = ""
) -> Certificate:
    """Draw a certificate again with the template as it is now, keeping its number.

    An administrator can correct the name at the same time. Reissuing a revoked certificate makes it
    valid again, which is how a mistaken revocation is undone.
    """
    with transaction.atomic():
        certificate = _get(certificate_id)
        before = {
            "holder_name": certificate.holder_name,
            "version": certificate.template.get("version"),
            "revoked": certificate.revoked_at is not None,
        }
        if holder_name is not None:
            clean = plain(holder_name)[:160]
            if not clean:
                raise exceptions.ValidationError({"holder_name": ["This field may not be blank."]})
            certificate.holder_name = clean
        certificate.revoked_at = None
        certificate.revoked_reason = ""
        certificate.template = snapshot_of(current_settings())
        certificate.save(
            update_fields=["holder_name", "revoked_at", "revoked_reason", "template", "updated_at"]
        )
        analytics.track(
            "certificate_reissued",
            actor_id=getattr(actor, "pk", None),
            properties={"course_id": certificate.enrolment.course.slug},
        )
        audit.record(
            actor=actor,
            action="certificates.reissued",
            target_type="certificate",
            target_id=certificate.pk,
            before=before,
            after={
                "holder_name": certificate.holder_name,
                "version": certificate.template["version"],
                "revoked": False,
            },
            ip=ip,
        )
    store_pdf(certificate)
    notify.notify(
        certificate.enrolment.user_id,
        "certificate_ready",
        {"certificate_id": str(certificate.pk), "title": certificate.course_title},
        dedupe_key=f"certificate:{certificate.pk}:{uuid4().hex[:8]}",
    )
    return certificate


def listed(*, q: str = "", status: str = "") -> Any:
    rows = Certificate.objects.select_related("enrolment__course", "enrolment__user").order_by(
        "-issued_at", "-id"
    )
    if status == "valid":
        rows = rows.filter(revoked_at__isnull=True)
    elif status == "revoked":
        rows = rows.filter(revoked_at__isnull=False)
    if q.strip():
        term = q.strip()
        rows = rows.filter(
            Q(code__icontains=term)
            | Q(holder_name__icontains=term)
            | Q(course_title__icontains=term)
            | Q(enrolment__user__email__icontains=term)
        )
    return rows
