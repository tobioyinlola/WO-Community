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
