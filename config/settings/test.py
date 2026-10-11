import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgres://wo:wo@localhost:5433/wo")

from cryptography.fernet import Fernet  # noqa: E402

from .base import *  # noqa: E402,F403
from .base import REST_FRAMEWORK as _REST_FRAMEWORK  # noqa: E402
from .keys import ephemeral_jwt_keys  # noqa: E402

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = ephemeral_jwt_keys()
FIELD_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
REST_FRAMEWORK = {
    **_REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": dict.fromkeys(_REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "1000/min"),
}

REFRESH_COOKIE_SECURE = False
ANALYTICS_STRICT = True
ANALYTICS_FORWARD_DELAY_SECONDS = 0
ANALYTICS_SINK = "apps.integrations.analytics.sinks.FakeSink"
CDN_PURGER = "apps.integrations.cdn.fake.FakePurger"
STORAGE_ADAPTER = "apps.integrations.storage.fake.FakeStorage"
MALWARE_SCANNER = "apps.integrations.malware.fake.FakeScanner"
MEDIA_BASE_URL = "https://media.test"
RESEND_API_KEY = "re_test_key"  # noqa: S105  # nosec B105
# "whsec_" followed by base64 of a throwaway key, the format Resend/Svix issue.
RESEND_WEBHOOK_SECRET = (
    "whsec_dGVzdC13ZWJob29rLXNlY3JldC0xMjM0NTY3ODkwMTI="  # noqa: S105  # nosec B105
)
EMAIL_FROM_TRANSACTIONAL = "WO Community <no-reply@mail.test>"
EMAIL_FROM_MARKETING = "WO Community <community@news.test>"
PASSWORD_BREACH_CHECKER = (
    "apps.integrations.passwords.fake.FakeBreachChecker"  # noqa: S105  # nosec B105
)
FRONTEND_BASE_URL = "https://app.test"
LINK_PREVIEW_FETCHER = "apps.integrations.linkpreview.fake.FakeFetcher"
GOOGLE_CLIENT_ID = "test-client.apps.googleusercontent.com"
GOOGLE_TOKEN_VERIFIER = (
    "apps.integrations.identity.fake.FakeGoogleVerifier"  # noqa: S105  # nosec B105
)

SERVE_API_SCHEMA = True
