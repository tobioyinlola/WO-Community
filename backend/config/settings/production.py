from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from config.env import env, first, require

from .base import *  # noqa: F403
from .base import (
    ALLOWED_HOSTS,
    API_BASE_URL,
    CORS_ALLOWED_ORIGINS,
    CSRF_TRUSTED_ORIGINS,
    DATABASES,
    FRONTEND_BASE_URL,
    NUM_PROXIES,
    REFRESH_COOKIE_SECURE,
)

# Anything a deployment can get wrong is checked here, so a bad setting stops the process at start
# up with a message that names the variable, instead of failing on the first request.
DEBUG = env.bool("DEBUG", default=False)
if DEBUG:
    raise ImproperlyConfigured("DEBUG must be false in production.")


# For trying these settings on one machine, where there is no https and the hosts are localhost.
# It switches off the https and localhost checks and the https redirect, and nothing else. Never set
# it on a real deployment.
LOCAL_PRODUCTION_RUN = env.bool("LOCAL_PRODUCTION_RUN", default=False)


def _https_origin(name: str, value: str, allow_path: bool = False) -> None:
    if LOCAL_PRODUCTION_RUN:
        return
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname == "localhost":
        raise ImproperlyConfigured(f"{name} must be a public https address, got {value!r}.")
    if not allow_path and parsed.path not in ("", "/"):
        raise ImproperlyConfigured(f"{name} must be an origin with no path, got {value!r}.")


if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list the API host, never '*'.")
# Railway's own health check calls the service by this name.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "healthcheck.railway.app"]
if not first("REDIS_URL", "CELERY_BROKER_URL"):
    raise ImproperlyConfigured("Environment variable REDIS_URL is required")
if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("Environment variable CORS_ALLOWED_ORIGINS is required")
for _origin in CORS_ALLOWED_ORIGINS:
    _https_origin("CORS_ALLOWED_ORIGINS", _origin)
_https_origin("FRONTEND_URL", FRONTEND_BASE_URL)
_https_origin("API_BASE_URL", API_BASE_URL)
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [*CORS_ALLOWED_ORIGINS, API_BASE_URL]
if NUM_PROXIES < 1:
    raise ImproperlyConfigured(
        "NUM_PROXIES must be at least 1 behind the platform proxy, or every visitor shares one "
        "rate limit."
    )
if not REFRESH_COOKIE_SECURE:
    raise ImproperlyConfigured("REFRESH_COOKIE_SECURE must stay true in production.")

JWT_PRIVATE_KEY = require("JWT_PRIVATE_KEY").replace("\\n", "\n")
JWT_PUBLIC_KEY = require("JWT_PUBLIC_KEY").replace("\\n", "\n")

SECURE_SSL_REDIRECT = not LOCAL_PRODUCTION_RUN
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# The platform's health checks arrive over plain HTTP inside its network.
SECURE_REDIRECT_EXEMPT = [r"^health/"]

DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env.str("DB_SSLMODE", default="require")
# Statement and idle-in-transaction timeouts are applied at database role level.

EMAIL_ADAPTER = require("EMAIL_ADAPTER")
if EMAIL_ADAPTER.endswith("ResendEmailAdapter"):
    require("RESEND_API_KEY")
    require("RESEND_WEBHOOK_SECRET")
    require("EMAIL_FROM_TRANSACTIONAL")
    require("EMAIL_FROM_MARKETING")
require("FIELD_ENCRYPTION_KEYS")
# Production must not run on the in-memory storage or scanner.
STORAGE_ADAPTER = require("STORAGE_ADAPTER")
MALWARE_SCANNER = require("MALWARE_SCANNER")
MEDIA_BASE_URL = require("MEDIA_BASE_URL")
_https_origin("MEDIA_BASE_URL", MEDIA_BASE_URL, allow_path=True)
if STORAGE_ADAPTER.endswith("S3Storage"):
    require("STORAGE_ACCESS_KEY_ID")
    require("STORAGE_SECRET_ACCESS_KEY")
    if STORAGE_UPLOAD_METHOD not in ("post", "put"):  # noqa: F405
        raise ImproperlyConfigured("STORAGE_UPLOAD_METHOD must be 'post' or 'put'.")

# Partitions are archived before they are dropped, and the audit head hash is anchored.
ANALYTICS_REQUIRE_ARCHIVE = True
# Google sign-in is optional, but once a client id is set the real verifier must check the tokens.
if GOOGLE_CLIENT_ID and GOOGLE_TOKEN_VERIFIER.endswith("FakeGoogleVerifier"):  # noqa: F405
    raise RuntimeError("GOOGLE_TOKEN_VERIFIER must not be the fake verifier in production.")

# Booked sessions need a real video meeting provider; the fake one only makes up addresses.
_default_meetings = MEETING_PROVIDERS[MEETING_DEFAULT_PROVIDER]  # noqa: F405
if _default_meetings.endswith("FakeMeetingProvider"):
    raise RuntimeError("The default meeting provider must not be the fake provider in production.")
if _default_meetings.endswith("GoogleMeetProvider"):
    require("GOOGLE_MEET_CLIENT_ID")
    require("GOOGLE_MEET_CLIENT_SECRET")
    require("GOOGLE_MEET_REFRESH_TOKEN")
if _default_meetings.endswith("ZoomProvider"):
    require("ZOOM_ACCOUNT_ID")
    require("ZOOM_CLIENT_ID")
    require("ZOOM_CLIENT_SECRET")

# The launch toolkit needs a real model and a real research source, or its tools switched off.
if any(TOOLKIT_FEATURES.values()):  # noqa: F405
    if AI_PROVIDER == "fake":  # noqa: F405
        raise RuntimeError(
            "AI_PROVIDER must name a real provider in production, or switch the toolkit tools "
            "off with TOOLKIT_FEATURE_<NAME>=false."
        )
    if AI_PROVIDER == "http":  # noqa: F405
        require("AI_BASE_URL")
        require("AI_API_KEY")
    if RESEARCH_PROVIDER.endswith("FakeResearchProvider"):  # noqa: F405
        raise RuntimeError("RESEARCH_PROVIDER must not be the fake provider in production.")
    _reads_web = RESEARCH_PROVIDER.endswith("WebResearchProvider")  # noqa: F405
    if _reads_web and not RESEARCH_ALLOWED_DOMAINS:  # noqa: F405
        raise RuntimeError("RESEARCH_ALLOWED_DOMAINS must list the sites research may read.")

# Public pages are cached by the CDN; a change must be able to purge them.
if CDN_PURGER.endswith("CloudflarePurger"):  # noqa: F405
    require("CLOUDFLARE_API_TOKEN")
    require("CLOUDFLARE_ZONE_ID")
    require("CDN_ORIGIN_URL")
