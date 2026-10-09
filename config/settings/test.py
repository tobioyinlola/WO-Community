import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgres://wo:wo@localhost:5433/wo")

from .base import *  # noqa: E402,F403
from .base import REST_FRAMEWORK as _REST_FRAMEWORK  # noqa: E402
from .keys import ephemeral_jwt_keys  # noqa: E402

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = ephemeral_jwt_keys()
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
REST_FRAMEWORK = {
    **_REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": dict.fromkeys(_REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "1000/min"),
}

REFRESH_COOKIE_SECURE = False
FRONTEND_BASE_URL = "https://app.test"
