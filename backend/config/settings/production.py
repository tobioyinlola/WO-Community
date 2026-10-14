from config.env import env

# The first import checks every variable and reports all the problems at once. It must stay above
# `base`, which stops at the first variable it cannot read.
from . import _production_check  # noqa: F401
from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS, API_BASE_URL, CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS, DATABASES

# Everything a deployment can get wrong (missing variables, http addresses, localhost, the fake
# adapters, mismatched keys) is checked in `config/env_check.py`, so a bad setting stops the process
# at start up with one message that names every variable, instead of failing on the first request.
DEBUG = False

# For trying these settings on one machine, where there is no https and the hosts are localhost.
# It switches off the https and localhost checks and the https redirect, and nothing else. Never set
# it on a real deployment.
LOCAL_PRODUCTION_RUN = env.bool("LOCAL_PRODUCTION_RUN", default=False)

# Railway's own health check calls the service by this name.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "healthcheck.railway.app"]
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [*CORS_ALLOWED_ORIGINS, API_BASE_URL]

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

# Partitions are archived before they are dropped, and the audit head hash is anchored.
ANALYTICS_REQUIRE_ARCHIVE = True
