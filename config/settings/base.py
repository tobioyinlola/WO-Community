from datetime import timedelta

import structlog
from kombu import Exchange, Queue

from apps.core.logging import shared_processors
from config.env import BASE_DIR, env, require

SECRET_KEY = require("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "apps.core",
    "apps.analytics",
    "apps.integrations",
    "apps.audit",
    "apps.reference",
    "apps.accounts",
    "apps.uploads",
    "apps.profiles",
    "apps.startups",
    "apps.directory",
    "apps.memberarea",
    "apps.feed",
    "apps.jobs",
    "apps.editorial",
    "apps.notifications",
    "apps.adminconsole",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES: list[dict] = []

AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DATABASES = {
    "default": {
        **env.db("DATABASE_URL"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env.str("REDIS_CACHE_URL", default="redis://localhost:6380/1"),
        "KEY_PREFIX": "wo",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "apps.integrations.passwords.validator.NotBreachedValidator"},
]
PASSWORD_BREACH_CHECKER = env.str(
    "PASSWORD_BREACH_CHECKER", default="apps.integrations.passwords.hibp.HibpBreachChecker"
)
# Google sign-in is off until a client id is configured.
GOOGLE_CLIENT_ID = env.str("GOOGLE_CLIENT_ID", default="")
GOOGLE_TOKEN_VERIFIER = env.str(
    "GOOGLE_TOKEN_VERIFIER", default="apps.integrations.identity.google.GoogleTokenVerifier"
)

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Requests are small JSON documents; uploads go straight to object storage.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_048_576
FILE_UPLOAD_MAX_MEMORY_SIZE = 262_144

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["X-Request-ID", "ETag"]
CORS_ALLOW_HEADERS = [
    "authorization",
    "content-type",
    "idempotency-key",
    "if-match",
    "x-requested-with",
]

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.core.permissions.PolicyPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "apps.core.errors.problem_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultCursorPagination",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "300/min",
        "auth_register": "5/hour",
        "auth_login": "30/min",
        "auth_google": "30/min",
        "search": "60/min",
        "feed_read": "240/min",
        "auth_forgot": "5/hour",
        "auth_token": "20/hour",
        "auth_refresh": "60/min",
        "auth_mfa": "20/min",
        "admin_bulk": "10/hour",
        "public_search": "60/min",
        "uploads": "30/hour",
        "analytics": "120/min",
    },
    "NUM_PROXIES": env.int("NUM_PROXIES", default=0),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "WO Community API",
    "DESCRIPTION": "REST API for the WO Community platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "JobTypeEnum": "apps.jobs.models.JOB_TYPES",
        "ApplyMethodEnum": "apps.jobs.models.APPLY_METHODS",
        "EditorialTypeEnum": "apps.editorial.models.ITEM_TYPES",
        "WinKindEnum": "apps.editorial.models.WIN_KINDS",
        "ReactionKindEnum": "apps.feed.models.REACTION_KINDS",
    },
}

# Comma separated Fernet keys; the first encrypts, all decrypt (see apps/core/crypto.py).
FIELD_ENCRYPTION_KEYS = env.list("FIELD_ENCRYPTION_KEYS", default=[])

# --- Authentication tokens -------------------------------------------------
JWT_ISSUER = env.str("JWT_ISSUER", default="wo-community")
JWT_ALGORITHM = "EdDSA"
JWT_PRIVATE_KEY = env.str("JWT_PRIVATE_KEY", default="").replace("\\n", "\n")
JWT_PUBLIC_KEY = env.str("JWT_PUBLIC_KEY", default="").replace("\\n", "\n")
JWT_ACCESS_LIFETIME = timedelta(minutes=10)

# --- Accounts ----------------------------------------------------------------
FRONTEND_BASE_URL = env.str("FRONTEND_BASE_URL", default="http://localhost:5173")
EMAIL_VERIFY_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(hours=1)
REFRESH_SLIDING_LIFETIME = timedelta(days=30)
REFRESH_ABSOLUTE_LIFETIME = timedelta(days=90)
REFRESH_COOKIE_NAME = "wo_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"
REFRESH_COOKIE_SECURE = env.bool("REFRESH_COOKIE_SECURE", default=True)
LOGIN_MAX_FAILURES_PER_ACCOUNT = 5
LOGIN_MAX_FAILURES_PER_IP = 30
LOGIN_FAILURE_WINDOW_SECONDS = 600
PASSWORD_RESET_MAX_PER_EMAIL_PER_HOUR = 3
# Destructive admin actions need an MFA check no older than this.
STEP_UP_MAX_AGE_SECONDS = 600
INVITATION_TTL = timedelta(days=7)
INVITATION_MAX_MESSAGE_LENGTH = 500
INVITATION_BULK_MAX_ROWS = 500
INVITATION_BULK_MAX_BYTES = 256_000
# An admin session must have passed MFA within this window, however often it refreshes.
MFA_SESSION_MAX_AGE_SECONDS = 43200
MFA_ISSUER = "WO Community"
MFA_CHALLENGE_TTL_SECONDS = 300
MFA_MAX_FAILURES = 5
MFA_FAILURE_WINDOW_SECONDS = 600
MFA_RECOVERY_CODE_COUNT = 10
# Versions of the documents a member accepts at registration.
CONSENT_DOCUMENT_VERSIONS = {"terms": "1", "privacy": "1", "conduct": "1", "marketing": "1"}

# --- Celery ------------------------------------------------------------------
CELERY_BROKER_URL = env.str("CELERY_BROKER_URL", default="redis://localhost:6380/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_SOFT_TIME_LIMIT = 120
CELERY_TASK_TIME_LIMIT = 150
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_QUEUES = (
    Queue("critical", Exchange("critical"), routing_key="critical"),
    Queue("default", Exchange("default"), routing_key="default"),
    Queue("email", Exchange("email"), routing_key="email"),
    Queue("media", Exchange("media"), routing_key="media"),
    Queue("exports", Exchange("exports"), routing_key="exports"),
    Queue("analytics", Exchange("analytics"), routing_key="analytics"),
)
CELERY_TASK_ROUTES = {
    "core.dispatch_outbox": {"queue": "critical"},
    "analytics.forward": {"queue": "analytics"},
    "analytics.ensure_partitions": {"queue": "analytics"},
    "analytics.drop_expired": {"queue": "analytics"},
    "feed.fetch_link_preview": {"queue": "media"},
}
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "dispatch-outbox": {"task": "core.dispatch_outbox", "schedule": 5.0},
    "purge-outbox": {"task": "core.purge_outbox", "schedule": 86400.0},
    "notifications-purge-webhooks": {"task": "notifications.purge_webhooks", "schedule": 86400.0},
    "notifications-purge": {"task": "notifications.purge_notifications", "schedule": 86400.0},
    "feed-purge-link-previews": {"task": "feed.purge_link_previews", "schedule": 86400.0},
    "jobs-expire": {"task": "jobs.expire_due", "schedule": 900.0},
    "editorial-publish-due": {"task": "editorial.publish_due", "schedule": 60.0},
    "jobs-warn-expiring": {"task": "jobs.warn_expiring", "schedule": 3600.0},
    "jobs-digests": {"task": "jobs.send_digests", "schedule": 3600.0},
    "analytics-forward": {"task": "analytics.forward", "schedule": 60.0},
    "analytics-partitions": {"task": "analytics.ensure_partitions", "schedule": 86400.0},
    "analytics-retention": {"task": "analytics.drop_expired", "schedule": 86400.0},
    "uploads-cleanup": {"task": "uploads.cleanup", "schedule": 3600.0},
    "directory-reconcile": {"task": "directory.reconcile", "schedule": 3600.0},
    "audit-ensure-partitions": {"task": "audit.ensure_partitions", "schedule": 86400.0},
    "audit-verify-chain": {"task": "audit.verify_previous_day", "schedule": 86400.0},
}
OUTBOX_MAX_ATTEMPTS = 8

# --- Adapters ----------------------------------------------------------------
EMAIL_ADAPTER = env.str("EMAIL_ADAPTER", default="apps.integrations.email.fake.FakeEmailAdapter")
# --- Email (Resend) ----------------------------------------------------------
RESEND_API_KEY = env.str("RESEND_API_KEY", default="")
RESEND_WEBHOOK_SECRET = env.str("RESEND_WEBHOOK_SECRET", default="")
# Transactional and marketing mail use different sending addresses (ideally different
# subdomains) so a marketing complaint cannot damage the standing of password resets.
EMAIL_FROM_TRANSACTIONAL = env.str(
    "EMAIL_FROM_TRANSACTIONAL", default="WO Community <no-reply@localhost>"
)
EMAIL_FROM_MARKETING = env.str("EMAIL_FROM_MARKETING", default="WO Community <community@localhost>")
EMAIL_REPLY_TO = env.str("EMAIL_REPLY_TO", default="")
EMAIL_WEBHOOK_RETENTION_DAYS = 30

CDN_PURGER = env.str("CDN_PURGER", default="apps.integrations.cdn.fake.LoggingPurger")
STORAGE_ADAPTER = env.str("STORAGE_ADAPTER", default="apps.integrations.storage.fake.FakeStorage")
MALWARE_SCANNER = env.str("MALWARE_SCANNER", default="apps.integrations.malware.fake.FakeScanner")

# --- Analytics ---------------------------------------------------------------
# Raise on a bad event (tests, local) instead of dropping it quietly (production).
ANALYTICS_STRICT = env.bool("ANALYTICS_STRICT", default=False)
ANALYTICS_RETENTION_MONTHS = 13
ANALYTICS_FORWARD_BATCH = 500
# Events are forwarded only once this old, so one numbered early that commits late is not skipped.
ANALYTICS_FORWARD_DELAY_SECONDS = 60
ANALYTICS_SINK = env.str("ANALYTICS_SINK", default="apps.integrations.analytics.sinks.LoggingSink")
# Who is calling /events: a signed-in member if there is a valid token, otherwise anonymous.
ANALYTICS_AUTHENTICATION = ["apps.accounts.authentication.OptionalJWTAuthentication"]

# --- Uploads and media -------------------------------------------------------
STORAGE_ENDPOINT_URL = env.str("STORAGE_ENDPOINT_URL", default="")  # set for MinIO
STORAGE_REGION = env.str("STORAGE_REGION", default="us-east-1")
STORAGE_ACCESS_KEY_ID = env.str("STORAGE_ACCESS_KEY_ID", default="")
STORAGE_SECRET_ACCESS_KEY = env.str("STORAGE_SECRET_ACCESS_KEY", default="")
STORAGE_QUARANTINE_BUCKET = env.str("STORAGE_QUARANTINE_BUCKET", default="wo-quarantine")
STORAGE_MEDIA_BUCKET = env.str("STORAGE_MEDIA_BUCKET", default="wo-media")
# Public address of the media bucket: a separate, cookieless domain behind the CDN.
MEDIA_BASE_URL = env.str("MEDIA_BASE_URL", default="http://localhost:9000/wo-media")
CLAMD_HOST = env.str("CLAMD_HOST", default="localhost")
CLAMD_PORT = env.int("CLAMD_PORT", default=3310)
CLAMD_TIMEOUT = 10
UPLOAD_ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp")
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_PRESIGN_TTL_SECONDS = 900
UPLOAD_DAILY_LIMIT = 20
UPLOAD_PROCESSING_TIMEOUT = timedelta(hours=2)
UPLOAD_UNCLAIMED_TTL = timedelta(hours=24)
UPLOAD_RECORD_RETENTION = timedelta(days=7)
IMAGE_MAX_PIXELS = 25_000_000
IMAGE_MAX_SIDE = 10_000
IMAGE_LARGE_SIDE = 1600
IMAGE_THUMB_SIDE = 320
IMAGE_QUALITY = 85

# --- Observability -----------------------------------------------------------
SENTRY_DSN = env.str("SENTRY_DSN", default="")
ENVIRONMENT = env.str("ENVIRONMENT", default="local")
RELEASE = env.str("RELEASE", default="dev")
LOG_LEVEL = env.str("LOG_LEVEL", default="INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "structlog.stdlib.ProcessorFormatter",
            "processors": [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
            "foreign_pre_chain": shared_processors,
        },
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django.server": {"level": "WARNING"}},
}

# Payments stay dark until Stage 4.
FEATURE_PAYMENTS_ENABLED = env.bool("FEATURE_PAYMENTS_ENABLED", default=False)

# Email uniqueness is enforced case-insensitively by a functional constraint on
# lower(email) instead of a plain unique column, which these checks cannot see.
SILENCED_SYSTEM_CHECKS = ["auth.E003", "auth.W004"]

# Feed limits per member, to keep spam and floods in check.
FEED_POSTS_PER_DAY = env.int("FEED_POSTS_PER_DAY", default=20)
FEED_COMMENTS_PER_DAY = env.int("FEED_COMMENTS_PER_DAY", default=200)
FEED_MAX_IMAGES = 10
LINK_PREVIEW_FETCHER = env.str(
    "LINK_PREVIEW_FETCHER", default="apps.integrations.linkpreview.fetcher.WebFetcher"
)
FEED_REPORTS_PER_DAY = env.int("FEED_REPORTS_PER_DAY", default=20)
