"""Checks the production environment as a whole and reports everything wrong in one message.

The production settings used to stop at the first missing variable, so a deploy took one failed
start per variable. `check` goes through all of them and returns every problem with the variable
name and a short hint. It reads only environment variables, never Django settings, so it can run
before any settings load (the production settings call it first) and from `manage.py check_env`
even when the settings would refuse to load.

Secrets are never printed: a problem names the variable and says what is wrong, and only addresses
(which are not secret) are quoted back.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

Getter = Callable[[str], str]

DOCS = "docs/deployment/railway-variables.md"

TRUE = {"1", "true", "yes", "on", "t", "y"}
PLACEHOLDERS = ("change-me", "changeme", "replace-me", "your-secret", "local-development")

FAKE_EMAIL = "apps.integrations.email.fake.FakeEmailAdapter"
FAKE_MEETINGS = "apps.integrations.meetings.fake.FakeMeetingProvider"
FAKE_RESEARCH = "apps.toolkit.ai.research.fake.FakeResearchProvider"
LOGGING_PURGER = "apps.integrations.cdn.fake.LoggingPurger"
EMAIL_ADAPTERS = (
    "apps.integrations.email.resend.ResendEmailAdapter",
    "apps.integrations.email.smtp.SmtpEmailAdapter",
    FAKE_EMAIL,
)
TOOLKIT_TOOLS = ("score", "plan", "forecast", "decks", "prototypes", "partner")

SECRET_HINT = (
    'python -c "import secrets; print(secrets.token_urlsafe(64))"'  # noqa: S105 - a command
)
FERNET_HINT = (
    'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
)
JWT_HINT = (
    "An Ed25519 PEM key on one line with \\n between the lines and no quotes. "
    f"The command that makes a pair is in {DOCS}."
)


@dataclass(frozen=True)
class Finding:
    name: str
    problem: str
    hint: str = ""


@dataclass
class Report:
    problems: list[Finding]
    warnings: list[Finding]

    @property
    def ok(self) -> bool:
        return not self.problems


def _truthy(value: str) -> bool:
    return value.strip().lower() in TRUE


class _Checker:
    def __init__(self, get: Getter) -> None:
        self.get = get
        self.problems: list[Finding] = []
        self.warnings: list[Finding] = []
        self.local_run = _truthy(get("LOCAL_PRODUCTION_RUN"))

    # -- reading -------------------------------------------------------------------------

    def first(self, *names: str) -> str:
        for name in names:
            value = self.get(name).strip()
            if value:
                return value
        return ""

    def need(self, name: str, hint: str, *aliases: str) -> str:
        """The value of a required variable, or a problem if it is not set."""
        value = self.first(name, *aliases)
        if not value:
            label = f"{name} (or {' or '.join(aliases)})" if aliases else name
            self.problem(name, f"Environment variable {label} is required.", hint)
        return value

    def csv(self, value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    # -- reporting -----------------------------------------------------------------------

    def problem(self, name: str, text: str, hint: str = "") -> None:
        self.problems.append(Finding(name, text, hint))

    def warn(self, name: str, text: str, hint: str = "") -> None:
        self.warnings.append(Finding(name, text, hint))

    # -- shared rules --------------------------------------------------------------------

    def https(self, name: str, value: str, *, allow_path: bool = False) -> None:
        """A public https address. A trial run of the settings on one machine skips it."""
        if not value or self.local_run:
            return
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname == "localhost":
            self.problem(
                name,
                f"{name} must be a public https address, got {value!r}.",
                "Use the full address, for example https://app.example.com",
            )
        elif not allow_path and parsed.path not in ("", "/"):
            self.problem(
                name,
                f"{name} must be an origin with no path, got {value!r}.",
                "Remove everything after the host name.",
            )

    def dotted(self, name: str, value: str, allowed: Sequence[str] = ()) -> None:
        """A dotted path to a class: the module must exist, and match the list if one is given."""
        if not value:
            return
        module, _, cls = value.rpartition(".")
        if not module or not cls:
            self.problem(
                name, f"{name} must be a dotted path to a class, got {value!r}.", _options(allowed)
            )
            return
        if allowed and value not in allowed:
            self.problem(
                name, f"{name} is not one of the known adapters, got {value!r}.", _options(allowed)
            )
            return
        try:
            found = importlib.util.find_spec(module)
        except (ImportError, ValueError):
            found = None
        if found is None:
            self.problem(
                name, f"{name} points at a module that does not exist: {module}.", _options(allowed)
            )


def _options(allowed: Sequence[str]) -> str:
    return (
        "Allowed: " + "; ".join(allowed)
        if allowed
        else "Check the spelling of the module and class."
    )


# ---------------------------------------------------------------------------------------------


def check(get: Getter) -> Report:
    """Every problem with the production environment. `get` returns a variable's value or ''."""
    c = _Checker(get)
    _core(c)
    _addresses(c)
    _keys(c)
    _email(c)
    _storage(c)
    _meetings(c)
    _toolkit(c)
    _cdn_and_identity(c)
    return Report(c.problems, c.warnings)


def _core(c: _Checker) -> None:
    if _truthy(c.get("DEBUG")):
        c.problem("DEBUG", "DEBUG must be false in production.", "Remove DEBUG or set it to false.")

    secret = c.need("DJANGO_SECRET_KEY", f"A long random string: {SECRET_HINT}", "SECRET_KEY")
    if secret and secret.lower().startswith(PLACEHOLDERS):
        c.problem("DJANGO_SECRET_KEY", "DJANGO_SECRET_KEY is still a placeholder.", SECRET_HINT)
    elif secret and (len(secret) < 50 or len(set(secret)) < 5):
        c.warn("DJANGO_SECRET_KEY", "DJANGO_SECRET_KEY is short or repetitive.", SECRET_HINT)

    hosts = c.csv(
        c.need(
            "DJANGO_ALLOWED_HOSTS",
            "The API host name only, for example api.example.com",
            "ALLOWED_HOSTS",
        )
    )
    if "*" in hosts:
        c.problem(
            "DJANGO_ALLOWED_HOSTS",
            "DJANGO_ALLOWED_HOSTS must list the API host, never '*'.",
            "Use api.example.com",
        )
    elif any("://" in h or "/" in h for h in hosts):
        c.problem(
            "DJANGO_ALLOWED_HOSTS",
            "DJANGO_ALLOWED_HOSTS takes host names, not addresses.",
            "Write api.example.com, without https:// or a path.",
        )

    database = c.need("DATABASE_URL", "On Railway: ${{Postgres.DATABASE_URL}}")
    if database and not database.startswith(("postgres://", "postgresql://", "postgis://")):
        c.problem(
            "DATABASE_URL",
            "DATABASE_URL must be a PostgreSQL address (postgres://...).",
            "On Railway: ${{Postgres.DATABASE_URL}}",
        )

    redis = c.need("REDIS_URL", "On Railway: ${{Redis.REDIS_URL}}", "CELERY_BROKER_URL")
    if redis and not redis.startswith(("redis://", "rediss://")):
        c.problem(
            "REDIS_URL",
            "REDIS_URL must be a Redis address (redis:// or rediss://).",
            "On Railway: ${{Redis.REDIS_URL}}",
        )

    raw = c.get("NUM_PROXIES").strip()
    try:
        proxies = int(raw) if raw else 0
    except ValueError:
        proxies = -1
    if proxies < 1:
        c.problem(
            "NUM_PROXIES",
            "NUM_PROXIES must be at least 1 behind the platform proxy, "
            "or every visitor shares one rate limit.",
            "Set it to 1 on Railway.",
        )
    secure_cookie = c.get("REFRESH_COOKIE_SECURE").strip()
    if secure_cookie and not _truthy(secure_cookie):
        c.problem(
            "REFRESH_COOKIE_SECURE",
            "REFRESH_COOKIE_SECURE must stay true in production.",
            "Remove it or set it to true.",
        )


def _addresses(c: _Checker) -> None:
    origins = c.csv(
        c.need(
            "CORS_ALLOWED_ORIGINS",
            "The front end origin, https, for example https://app.example.com",
        )
    )
    for origin in origins:
        c.https("CORS_ALLOWED_ORIGINS", origin)
    c.https(
        "FRONTEND_URL",
        c.need(
            "FRONTEND_URL",
            "The front end, no trailing slash: https://app.example.com",
            "FRONTEND_BASE_URL",
        ),
    )
    c.https(
        "API_BASE_URL",
        c.need("API_BASE_URL", "This API, no trailing slash: https://api.example.com"),
    )
    for origin in c.csv(c.get("CSRF_TRUSTED_ORIGINS")):
        c.https("CSRF_TRUSTED_ORIGINS", origin)


def _keys(c: _Checker) -> None:
    private = c.need("JWT_PRIVATE_KEY", JWT_HINT).replace("\\n", "\n")
    public = c.need("JWT_PUBLIC_KEY", JWT_HINT).replace("\\n", "\n")
    _jwt(c, private, public)

    keys = c.csv(
        c.need(
            "FIELD_ENCRYPTION_KEYS",
            FERNET_HINT,
        )
    )
    if keys:
        from cryptography.fernet import Fernet

        for index, key in enumerate(keys, start=1):
            try:
                Fernet(key.encode())
            except (ValueError, TypeError):
                c.problem(
                    "FIELD_ENCRYPTION_KEYS",
                    f"Key {index} in FIELD_ENCRYPTION_KEYS is not a valid Fernet key.",
                    FERNET_HINT,
                )
                break


def _jwt(c: _Checker, private: str, public: str) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    loaded_private = loaded_public = None
    if private:
        try:
            loaded_private = serialization.load_pem_private_key(private.encode(), password=None)
        except (ValueError, TypeError):
            c.problem(
                "JWT_PRIVATE_KEY", "JWT_PRIVATE_KEY is not a readable PEM private key.", JWT_HINT
            )
        else:
            if not isinstance(loaded_private, Ed25519PrivateKey):
                c.problem(
                    "JWT_PRIVATE_KEY",
                    "JWT_PRIVATE_KEY must be an Ed25519 key (the algorithm is EdDSA).",
                    JWT_HINT,
                )
                loaded_private = None
    if public:
        try:
            loaded_public = serialization.load_pem_public_key(public.encode())
        except (ValueError, TypeError):
            c.problem(
                "JWT_PUBLIC_KEY", "JWT_PUBLIC_KEY is not a readable PEM public key.", JWT_HINT
            )
        else:
            if not isinstance(loaded_public, Ed25519PublicKey):
                c.problem(
                    "JWT_PUBLIC_KEY",
                    "JWT_PUBLIC_KEY must be an Ed25519 key (the algorithm is EdDSA).",
                    JWT_HINT,
                )
                loaded_public = None
    if loaded_private is not None and loaded_public is not None:
        raw = (serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        if loaded_private.public_key().public_bytes(*raw) != loaded_public.public_bytes(*raw):
            c.problem(
                "JWT_PUBLIC_KEY",
                "JWT_PUBLIC_KEY is not the public half of JWT_PRIVATE_KEY.",
                "Set both from one generated pair, or every sign in fails to verify.",
            )


def _email(c: _Checker) -> None:
    adapter = c.need("EMAIL_ADAPTER", f"One of: {'; '.join(EMAIL_ADAPTERS)}")
    c.dotted("EMAIL_ADAPTER", adapter, EMAIL_ADAPTERS)
    if adapter.endswith("ResendEmailAdapter"):
        key = c.need("RESEND_API_KEY", "Resend dashboard, API Keys (starts with re_)")
        if key and not key.startswith("re_"):
            c.warn(
                "RESEND_API_KEY",
                "RESEND_API_KEY does not start with re_.",
                "Check you copied the key, not the key's name.",
            )
        secret = c.need(
            "RESEND_WEBHOOK_SECRET",
            "Resend dashboard, Webhooks, Signing Secret (starts with whsec_)",
        )
        if secret and not secret.startswith("whsec_"):
            c.warn(
                "RESEND_WEBHOOK_SECRET",
                "RESEND_WEBHOOK_SECRET does not start with whsec_.",
                "Copy the signing secret of the webhook.",
            )
        for name, example in (
            ("EMAIL_FROM_TRANSACTIONAL", "WO Community <no-reply@mail.example.com>"),
            ("EMAIL_FROM_MARKETING", "WO Community <community@news.example.com>"),
        ):
            value = c.need(
                name,
                f"A verified Resend domain, for example {example}. "
                "DEFAULT_FROM_EMAIL sets both at once.",
                "DEFAULT_FROM_EMAIL",
            )
            if value and "@" not in value:
                c.problem(
                    name,
                    f"{name} must be an email address, optionally with a name.",
                    f"For example {example}",
                )
    elif adapter == FAKE_EMAIL:
        c.warn(
            "EMAIL_ADAPTER",
            "EMAIL_ADAPTER is the fake adapter: the app starts, but no email is sent.",
            "Members get no verification or reset mail. Use the Resend adapter for real use.",
        )
    elif adapter.endswith("SmtpEmailAdapter"):
        c.warn(
            "EMAIL_ADAPTER",
            "The SMTP adapter is for local mail catchers, not production.",
            "Use the Resend adapter.",
        )


def _storage(c: _Checker) -> None:
    storage = c.need(
        "STORAGE_ADAPTER", "apps.integrations.storage.s3.S3Storage (Cloudflare R2 or S3)"
    )
    scanner = c.need(
        "MALWARE_SCANNER", "apps.integrations.malware.clamd.ClamdScanner, with a ClamAV service"
    )
    c.dotted("STORAGE_ADAPTER", storage)
    c.dotted("MALWARE_SCANNER", scanner)
    c.https(
        "MEDIA_BASE_URL",
        c.need(
            "MEDIA_BASE_URL",
            "The public https address of the media bucket, for example https://media.example.com",
        ),
        allow_path=True,
    )
    if storage.endswith("S3Storage"):
        c.need(
            "STORAGE_ACCESS_KEY_ID",
            "An R2 or S3 access key id (Cloudflare dashboard, R2, API tokens)",
        )
        c.need(
            "STORAGE_SECRET_ACCESS_KEY", "The matching secret, shown once when the token is made"
        )
        method = c.get("STORAGE_UPLOAD_METHOD").strip() or "post"
        if method not in ("post", "put"):
            c.problem(
                "STORAGE_UPLOAD_METHOD",
                "STORAGE_UPLOAD_METHOD must be 'post' or 'put'.",
                "R2 needs put; S3 and MinIO use post.",
            )
    elif storage.endswith("FakeStorage"):
        c.warn(
            "STORAGE_ADAPTER",
            "STORAGE_ADAPTER is the in-memory fake: uploads are lost on restart.",
            "Use S3Storage.",
        )
    if scanner.endswith("FakeScanner"):
        c.warn(
            "MALWARE_SCANNER",
            "MALWARE_SCANNER is the fake: uploads are not scanned.",
            "Use ClamdScanner.",
        )


def _meetings(c: _Checker) -> None:
    provider = c.get("MEETING_DEFAULT_PROVIDER").strip() or "google_meet"
    adapters = {
        "google_meet": (
            "MEETING_GOOGLE_MEET_ADAPTER",
            "apps.integrations.meetings.google.GoogleMeetProvider",
        ),
        "zoom": ("MEETING_ZOOM_ADAPTER", "apps.integrations.meetings.zoom.ZoomProvider"),
    }
    if provider not in adapters:
        c.problem(
            "MEETING_DEFAULT_PROVIDER",
            f"MEETING_DEFAULT_PROVIDER must be google_meet or zoom, got {provider!r}.",
        )
        return
    name, real = adapters[provider]
    adapter = c.get(name).strip() or FAKE_MEETINGS
    if adapter == FAKE_MEETINGS:
        c.warn(
            name,
            f"No real meeting provider ({provider}): booked sessions get made-up links.",
            f"Optional. For real video links set {name}={real} and its credentials.",
        )
    elif adapter.endswith("GoogleMeetProvider"):
        c.need("GOOGLE_MEET_CLIENT_ID", "Google Cloud console, OAuth client")
        c.need("GOOGLE_MEET_CLIENT_SECRET", "Google Cloud console, OAuth client")
        c.need("GOOGLE_MEET_REFRESH_TOKEN", "The refresh token of the platform calendar's account")
    elif adapter.endswith("ZoomProvider"):
        c.need("ZOOM_ACCOUNT_ID", "Zoom marketplace, Server-to-Server OAuth app")
        c.need("ZOOM_CLIENT_ID", "Zoom marketplace, Server-to-Server OAuth app")
        c.need("ZOOM_CLIENT_SECRET", "Zoom marketplace, Server-to-Server OAuth app")


def _toolkit(c: _Checker) -> None:
    def enabled(tool: str) -> bool:
        value = c.get(f"TOOLKIT_FEATURE_{tool.upper()}").strip()
        return not value or _truthy(value)

    if not any(enabled(tool) for tool in TOOLKIT_TOOLS):
        return
    off_hint = (
        "or switch every tool off with TOOLKIT_FEATURE_<NAME>=false "
        "(SCORE, PLAN, FORECAST, DECKS, PROTOTYPES, PARTNER)"
    )
    provider = c.get("AI_PROVIDER").strip() or "fake"
    if provider == "fake":
        c.problem(
            "AI_PROVIDER",
            "AI_PROVIDER must name a real provider in production.",
            f"Set AI_PROVIDER=http with AI_BASE_URL and AI_API_KEY, {off_hint}.",
        )
    elif provider == "http":
        c.need("AI_BASE_URL", "An OpenAI compatible chat completions API address")
        c.need("AI_API_KEY", "The API key for that service")
    research = c.get("RESEARCH_PROVIDER").strip() or FAKE_RESEARCH
    if research == FAKE_RESEARCH:
        c.problem(
            "RESEARCH_PROVIDER",
            "RESEARCH_PROVIDER must not be the fake provider in production.",
            f"Set it to apps.toolkit.ai.research.web.WebResearchProvider, {off_hint}.",
        )
    elif research.endswith("WebResearchProvider") and not c.csv(c.get("RESEARCH_ALLOWED_DOMAINS")):
        c.problem(
            "RESEARCH_ALLOWED_DOMAINS",
            "RESEARCH_ALLOWED_DOMAINS must list the sites research may read.",
            "Comma separated domains, for example data.example.org",
        )


def _cdn_and_identity(c: _Checker) -> None:
    purger = c.get("CDN_PURGER").strip() or LOGGING_PURGER
    if purger.endswith("CloudflarePurger"):
        c.need("CLOUDFLARE_API_TOKEN", "Cloudflare dashboard, API token with cache purge")
        c.need("CLOUDFLARE_ZONE_ID", "Cloudflare dashboard, the zone's overview page")
        c.need("CDN_ORIGIN_URL", "The address Cloudflare fetches pages from, https")
    else:
        c.warn(
            "CDN_PURGER",
            "No CDN purger is set: a change to a public page will not clear the cached copy.",
            "Optional. See docs/deployment/cloudflare-r2.md.",
        )
    verifier = c.get("GOOGLE_TOKEN_VERIFIER").strip()
    if c.get("GOOGLE_CLIENT_ID").strip() and verifier.endswith("FakeGoogleVerifier"):
        c.problem(
            "GOOGLE_TOKEN_VERIFIER",
            "GOOGLE_TOKEN_VERIFIER must not be the fake verifier in production.",
            "Remove it to use the real verifier.",
        )


# ---------------------------------------------------------------------------------------------


def render(report: Report) -> str:
    """The report as text: every problem numbered, with its hint, then any warnings."""
    lines: list[str] = []
    if report.problems:
        count = len(report.problems)
        lines.append(
            f"The production settings are not complete: {count} "
            f"{'problem' if count == 1 else 'problems'}."
        )
        for number, finding in enumerate(report.problems, start=1):
            lines.append(f"  {number}. {finding.name}: {finding.problem}")
            if finding.hint:
                lines.append(f"     Hint: {finding.hint}")
        lines.append(f"Set these on the service, then deploy again. The full list is in {DOCS}.")
        lines.append(
            "Run `python manage.py check_env` to print this again without starting the server."
        )
    else:
        lines.append("All required production variables are set and valid.")
    if report.warnings:
        lines.append("")
        lines.append("Warnings (the app starts, but check these):")
        for finding in report.warnings:
            lines.append(f"  - {finding.name}: {finding.problem}")
            if finding.hint:
                lines.append(f"    {finding.hint}")
    return "\n".join(lines)


def _environment_getter() -> Getter:
    from config.env import env

    return lambda name: env.str(name, default="")


def enforce(get: Getter | None = None) -> None:
    """Stop the process with every problem at once if the environment is not fit for production."""
    report = check(get or _environment_getter())
    if not report.ok:
        raise ImproperlyConfigured("\n" + render(report))


def main(argv: Sequence[str] = ()) -> int:
    """`manage.py check_env`: print the report. The exit code is 1 when anything is missing."""
    report = check(_environment_getter())
    print(render(report))  # noqa: T201 - this is a command line report
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
