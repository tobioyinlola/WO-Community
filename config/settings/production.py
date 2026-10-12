from config.env import env, require

from .base import *  # noqa: F403
from .base import DATABASES

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
JWT_PRIVATE_KEY = require("JWT_PRIVATE_KEY").replace("\\n", "\n")
JWT_PUBLIC_KEY = require("JWT_PUBLIC_KEY").replace("\\n", "\n")

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Load balancer health checks arrive over plain HTTP inside the network.
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
