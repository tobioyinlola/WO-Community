"""Whether mail from this platform will be trusted: DNS records, streams, warm up and results.

What can be checked from here is checked (SPF, DKIM and DMARC records as the public DNS shows
them). What cannot be (whether a provider has verified the domain, or the sender's reputation)
is said plainly in ``docs/email-deliverability.md``.
"""

from datetime import timedelta
from email.utils import parseaddr
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.notifications import warmup
from apps.notifications.models import DeliveryEvent, Suppression

OK, WARN, MISSING, UNKNOWN = "ok", "warning", "missing", "unknown"


def sender_domain(sender: str) -> str:
    return parseaddr(sender)[1].rpartition("@")[2].lower()


def _check(key: str, label: str, status: str, detail: str, record: str = "") -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail, "record": record}


def _spf(txt: list[str] | None) -> dict[str, str]:
    if txt is None:
        return _check("spf", "SPF", UNKNOWN, "The lookup did not answer. Try again.")
    records = [t for t in txt if t.lower().startswith("v=spf1")]
    if not records:
        return _check(
            "spf", "SPF", MISSING, "No SPF record. Publish the one your provider gives you."
        )
    if len(records) > 1:
        return _check(
            "spf", "SPF", WARN, "More than one SPF record. Merge them into one.", records[0]
        )
    record = records[0]
    if "+all" in record or record.rstrip().endswith(" ?all"):
        return _check("spf", "SPF", WARN, "This SPF record lets any server send as you.", record)
    if not (record.rstrip().endswith("-all") or record.rstrip().endswith("~all")):
        return _check("spf", "SPF", WARN, "End the record with ~all or -all.", record)
    return _check("spf", "SPF", OK, "Published.", record)


def _dmarc(txt: list[str] | None) -> dict[str, str]:
    if txt is None:
        return _check("dmarc", "DMARC", UNKNOWN, "The lookup did not answer. Try again.")
    records = [t for t in txt if t.lower().startswith("v=dmarc1")]
    if not records:
        return _check(
            "dmarc",
            "DMARC",
            MISSING,
            "No DMARC record. Start with p=none and a report address.",
        )
    record = records[0]
    policy = next(
        (
            p.split("=", 1)[1].strip().lower()
            for p in record.split(";")
            if p.strip().startswith("p=")
        ),
        "",
    )
    if policy == "none":
        return _check(
            "dmarc",
            "DMARC",
            WARN,
            "Monitoring only (p=none). Once reports look clean, move to quarantine, then reject.",
            record,
        )
    return _check("dmarc", "DMARC", OK, f"Policy is {policy or 'set'}.", record)


def _dkim(domain: str, resolver: Any) -> dict[str, str]:
    found: list[str] = []
    failed = 0
    for selector in settings.EMAIL_DKIM_SELECTORS:
        txt = resolver.txt(f"{selector}._domainkey.{domain}")
        if txt is None:
            failed += 1
        elif any("p=" in t for t in txt):
            found.append(selector)
    if found:
        return _check("dkim", "DKIM", OK, f"Key published for: {', '.join(found)}.")
    if failed == len(settings.EMAIL_DKIM_SELECTORS):
        return _check("dkim", "DKIM", UNKNOWN, "The lookup did not answer. Try again.")
    return _check(
        "dkim",
        "DKIM",
        MISSING,
        "No DKIM key found for "
        + ", ".join(settings.EMAIL_DKIM_SELECTORS)
        + ". Publish the records your provider shows when you add the domain.",
    )


def check_domain(domain: str, stream: str, resolver: Any) -> dict[str, Any]:
    checks = [
        _spf(resolver.txt(domain)),
        _dkim(domain, resolver),
        _dmarc(resolver.txt(f"_dmarc.{domain}")),
    ]
    return {"domain": domain, "stream": stream, "checks": checks}


def health() -> dict[str, Any]:
    resolver = import_string(settings.EMAIL_DNS_RESOLVER)()
    transactional = sender_domain(settings.EMAIL_FROM_TRANSACTIONAL)
    marketing = sender_domain(settings.EMAIL_FROM_MARKETING)
    domains = [check_domain(transactional, "transactional", resolver)]
    if marketing != transactional:
        domains.append(check_domain(marketing, "broadcast", resolver))
    cap = warmup.hourly_cap(timezone.localdate())
    return {
        "provider": settings.EMAIL_ADAPTER.rsplit(".", 1)[-1].replace("EmailAdapter", "").lower(),
        "configured": {
            "api_key": bool(settings.RESEND_API_KEY),
            "webhook_secret": bool(settings.RESEND_WEBHOOK_SECRET),
            "reply_to": bool(settings.EMAIL_REPLY_TO),
            "logo": settings.EMAIL_LOGO_URL.startswith("https://"),
        },
        "separate_streams": marketing != transactional,
        "domains": domains,
        "hourly_cap": cap,
    }


def stats(days: int = 30) -> dict[str, Any]:
    since = timezone.now() - timedelta(days=days)
    counts = dict(
        DeliveryEvent.objects.filter(created_at__gte=since)
        .values_list("kind")
        .annotate(n=Count("id"))
        .order_by()
    )
    return {
        "days": days,
        "sent": counts.get("sent", 0),
        "delivered": counts.get("delivered", 0),
        "bounced": counts.get("bounced", 0) + counts.get("soft_bounced", 0),
        "complained": counts.get("complained", 0),
        "unsubscribed": Suppression.objects.filter(
            reason="unsubscribed", created_at__gte=since
        ).count(),
        "suppressed_total": Suppression.objects.count(),
    }


def recent_failures(limit: int = 30) -> list[DeliveryEvent]:
    return list(
        DeliveryEvent.objects.filter(
            kind__in=("bounced", "soft_bounced", "complained", "failed")
        ).order_by("-created_at")[:limit]
    )
