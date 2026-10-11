from datetime import timedelta

import structlog
from celery.schedules import crontab
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
    "apps.events",
    "apps.campaigns",
    "apps.learning",
    "apps.mentorship",
    "apps.toolkit.ventures",
    "apps.toolkit.jobs",
    "apps.toolkit.ai",
    "apps.toolkit.scoring",
    "apps.toolkit.plans",
    "apps.toolkit.forecasts",
    "apps.toolkit.decks",
    "apps.toolkit.prototypes",
    "apps.toolkit.partner",
    "apps.toolkit.sharing",
    "apps.toolkit.admin_api",
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
        "lesson_progress": "60/min",
        "lesson_visitor": "30/min",
        "toolkit_share": "60/min",
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
        "ChangeSetStatusEnum": "apps.toolkit.partner.models.CHANGE_STATUSES",
        "PrototypeKindEnum": "apps.toolkit.prototypes.spec.KINDS",
        "ShareSubjectTypeEnum": "apps.toolkit.sharing.models.SUBJECT_TYPES",
        "DeckStatusEnum": "apps.toolkit.decks.models.DECK_STATUSES",
        "PlanStatusEnum": "apps.toolkit.plans.models.PLAN_STATUSES",
        "PlanSectionStatusEnum": "apps.toolkit.plans.models.SECTION_STATUSES",
        "JobTypeEnum": "apps.jobs.models.JOB_TYPES",
        "ApplyMethodEnum": "apps.jobs.models.APPLY_METHODS",
        "EditorialTypeEnum": "apps.editorial.models.ITEM_TYPES",
        "WinKindEnum": "apps.editorial.models.WIN_KINDS",
        "EventTypeEnum": "apps.events.models.EVENT_TYPES",
        "LessonTypeEnum": "apps.learning.models.LESSON_TYPES",
        "MentorApplicationStatusEnum": "apps.mentorship.models.APPLICATION_STATUSES",
        "MentoringSessionStatusEnum": "apps.mentorship.models.SESSION_STATUSES",
        "CourseLevelEnum": "apps.learning.models.LEVELS",
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
    Queue("ai", Exchange("ai"), routing_key="ai"),
)
CELERY_TASK_ROUTES = {
    "core.dispatch_outbox": {"queue": "critical"},
    "analytics.forward": {"queue": "analytics"},
    "analytics.ensure_partitions": {"queue": "analytics"},
    "analytics.drop_expired": {"queue": "analytics"},
    "feed.fetch_link_preview": {"queue": "media"},
    "toolkit.run_ai_job": {"queue": "ai"},
    "toolkit.run_export_job": {"queue": "exports"},
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
    "events-reminders": {"task": "events.send_reminders", "schedule": 600.0},
    "news-digest": {
        "task": "memberarea.send_news_digest",
        "schedule": crontab(day_of_week="mon", hour=8, minute=0),
    },
    "mentorship-reminders": {"task": "mentorship.send_reminders", "schedule": 300.0},
    "mentorship-expire-requests": {"task": "mentorship.expire_requests", "schedule": 600.0},
    "mentorship-complete-due": {"task": "mentorship.complete_due", "schedule": 300.0},
    "mentorship-sync-calendars": {"task": "mentorship.sync_calendars", "schedule": 900.0},
    "campaigns-start-due": {"task": "campaigns.start_due", "schedule": 60.0},
    "dashboard-refresh": {"task": "adminconsole.refresh_dashboard", "schedule": 3600.0},
    "jobs-warn-expiring": {"task": "jobs.warn_expiring", "schedule": 3600.0},
    "jobs-digests": {"task": "jobs.send_digests", "schedule": 3600.0},
    "analytics-forward": {"task": "analytics.forward", "schedule": 60.0},
    "analytics-partitions": {"task": "analytics.ensure_partitions", "schedule": 86400.0},
    "analytics-archive": {"task": "analytics.archive_expired", "schedule": 86400.0},
    "analytics-retention": {"task": "analytics.drop_expired", "schedule": 86400.0},
    "audit-anchor": {"task": "audit.anchor_previous_day", "schedule": 86400.0},
    "toolkit-reap-jobs": {"task": "toolkit.reap_stuck_jobs", "schedule": 600.0},
    "toolkit-erase-ventures": {"task": "toolkit.erase_deleted_ventures", "schedule": 86400.0},
    "toolkit-purge-exports": {"task": "toolkit.purge_exports", "schedule": 3600.0},
    "toolkit-weekly-nudges": {
        "task": "toolkit.weekly_nudges",
        "schedule": crontab(day_of_week="mon", hour=7, minute=30),
    },
    "accounts-purge-rejected": {"task": "accounts.purge_rejected", "schedule": 86400.0},
    "uploads-cleanup": {"task": "uploads.cleanup", "schedule": 3600.0},
    "directory-reconcile": {"task": "directory.reconcile", "schedule": 3600.0},
    "audit-ensure-partitions": {"task": "audit.ensure_partitions", "schedule": 86400.0},
    "audit-verify-chain": {"task": "audit.verify_previous_day", "schedule": 86400.0},
}
OUTBOX_MAX_ATTEMPTS = 8

# --- Observability -------------------------------------------------------------
ENVIRONMENT = env.str("ENVIRONMENT", default="local")
# Tracing is off until a collector address is given. Spans never carry query strings.
OTEL_EXPORTER_OTLP_ENDPOINT = env.str("OTEL_EXPORTER_OTLP_ENDPOINT", default="")
OTEL_TRACE_SAMPLE_RATIO = env.float("OTEL_TRACE_SAMPLE_RATIO", default=0.1)
# GET /metrics answers only to this bearer token, and 404 when it is not set.
METRICS_TOKEN = env.str("METRICS_TOKEN", default="")

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
# Cloudflare: a token scoped to Cache Purge on one zone, and the public host behind it.
CLOUDFLARE_API_TOKEN = env.str("CLOUDFLARE_API_TOKEN", default="")
CLOUDFLARE_ZONE_ID = env.str("CLOUDFLARE_ZONE_ID", default="")
CDN_ORIGIN_URL = env.str("CDN_ORIGIN_URL", default="")
STORAGE_ADAPTER = env.str("STORAGE_ADAPTER", default="apps.integrations.storage.fake.FakeStorage")
MALWARE_SCANNER = env.str("MALWARE_SCANNER", default="apps.integrations.malware.fake.FakeScanner")

# --- Analytics ---------------------------------------------------------------
# Raise on a bad event (tests, local) instead of dropping it quietly (production).
ANALYTICS_STRICT = env.bool("ANALYTICS_STRICT", default=False)
ANALYTICS_RETENTION_MONTHS = 13
# When true, a monthly partition is dropped only after it was archived to Parquet.
ANALYTICS_REQUIRE_ARCHIVE = env.bool("ANALYTICS_REQUIRE_ARCHIVE", default=False)
# Registrations that were rejected are erased after this many days.
REJECTED_REGISTRATION_RETENTION_DAYS = 90
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
# Checked documents (course files). Never public: members are given short lived signed links.
STORAGE_PRIVATE_BUCKET = env.str("STORAGE_PRIVATE_BUCKET", default="wo-private")
# Write-once bucket (S3 Object Lock) for the daily audit head hash; never public.
STORAGE_ANCHOR_BUCKET = env.str("STORAGE_ANCHOR_BUCKET", default="wo-anchor")
AUDIT_ANCHOR_RETENTION_DAYS = env.int("AUDIT_ANCHOR_RETENTION_DAYS", default=7 * 365)
AUDIT_ANCHOR_VERIFY_DAYS = 7
# Public address of the media bucket: a separate, cookieless domain behind the CDN.
MEDIA_BASE_URL = env.str("MEDIA_BASE_URL", default="http://localhost:9000/wo-media")
CLAMD_HOST = env.str("CLAMD_HOST", default="localhost")
CLAMD_PORT = env.int("CLAMD_PORT", default=3310)
CLAMD_TIMEOUT = 10
UPLOAD_ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp")
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
# Documents are checked and scanned but, unlike images, cannot be rebuilt from their pixels, so
# they are only ever delivered as attachments through a short lived signed link.
UPLOAD_DOCUMENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}
UPLOAD_DOCUMENT_MAX_BYTES = 25 * 1024 * 1024
UPLOAD_DOCUMENT_MAX_UNPACKED_BYTES = 200 * 1024 * 1024  # a zip bomb guard for Office files
DOCUMENT_LINK_TTL_SECONDS = 300
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

# Newsletters: footer line, how fast a campaign sends, and the public API address that goes in
# one-click unsubscribe headers.
CAMPAIGN_FOOTER = env.str("CAMPAIGN_FOOTER", default="WO Community")
CAMPAIGN_BATCH_SIZE = env.int("CAMPAIGN_BATCH_SIZE", default=50)
CAMPAIGN_BATCH_DELAY_SECONDS = env.int("CAMPAIGN_BATCH_DELAY_SECONDS", default=5)
API_BASE_URL = env.str("API_BASE_URL", default="http://localhost:8000")

# Serve GET /api/v1/schema/. Off unless an environment turns it on.
SERVE_API_SCHEMA = env.bool("SERVE_API_SCHEMA", default=False)

# Mentorship: how far ahead and how soon sessions can be booked, and how matches are scored.
MENTORSHIP_MIN_NOTICE_HOURS = env.int("MENTORSHIP_MIN_NOTICE_HOURS", default=12)
MENTORSHIP_HORIZON_DAYS = 60
MENTORSHIP_RECOMMENDATION_TTL_SECONDS = 15 * 60
# Weights are relative; a signal with no data for a founder drops out and the rest are rescaled.
MENTORSHIP_MATCH_WEIGHTS = {
    "expertise": 0.35,
    "fit": 0.20,
    "availability": 0.15,
    "language": 0.10,
    "capacity": 0.10,
    "quality": 0.10,
}
# Words that mean the same thing when a founder describes a need and a mentor describes expertise.
MENTORSHIP_SYNONYMS = {
    "fundraising": ["investment", "raising capital", "venture capital", "investors"],
    "marketing": ["growth", "branding", "go-to-market"],
    "hiring": ["recruiting", "talent", "people"],
    "product": ["product management", "product design", "ux"],
    "legal": ["contracts", "compliance", "regulation"],
    "finance": ["accounting", "financial modelling", "budgeting"],
    "sales": ["business development", "revenue"],
}
# Sessions: how long a request waits, how many a founder can have open, and how late is late.
MENTORSHIP_REQUEST_TTL_HOURS = 72
MENTORSHIP_DECIDE_BEFORE_START_HOURS = 2  # an unanswered request lapses this long before it starts
MENTORSHIP_MAX_OPEN_REQUESTS = 5
MENTORSHIP_REQUESTS_PER_DAY = 10
MENTORSHIP_MAX_RESCHEDULES = 3
MENTORSHIP_LATE_CANCEL_HOURS = 24
MENTORSHIP_COMPLETE_AFTER_MINUTES = 15  # a confirmed session counts as held this long after it ends
MENTORSHIP_FEEDBACK_WINDOW_DAYS = 14

# --- Mentor calendar feeds ---------------------------------------------------
# A mentor can share the private iCal address of their calendar so busy time is not offered.
CALENDAR_FEED_READER = env.str(
    "CALENDAR_FEED_READER", default="apps.integrations.calendars.web.WebFeedReader"
)
CALENDAR_SYNC_DAYS = 62  # a little more than the booking horizon
CALENDAR_CONNECTS_PER_HOUR = 10
CALENDAR_STALE_AFTER = timedelta(hours=3)  # a feed not read for this long is shown as stale

# --- Venture launch toolkit ---------------------------------------------------
TOOLKIT_MAX_VENTURES_PER_MEMBER = env.int("TOOLKIT_MAX_VENTURES_PER_MEMBER", default=3)
# Each tool can ship (or be switched off) on its own.
TOOLKIT_FEATURES = {
    name: env.bool(f"TOOLKIT_FEATURE_{name.upper()}", default=True)
    for name in ("score", "plan", "forecast", "decks", "prototypes", "partner")
}
# "fake" runs offline; otherwise a dotted path to an LLMProvider class.
AI_PROVIDER = env.str("AI_PROVIDER", default="fake")
AI_FALLBACK_PROVIDER = env.str("AI_FALLBACK_PROVIDER", default="")
# Which model each kind of task uses, so routine steps can use a cheaper one.
AI_MODEL_ROUTING = {
    "default": env.str("AI_MODEL_DEFAULT", default="default-model"),
    "research": env.str("AI_MODEL_RESEARCH", default=""),
    "writer": env.str("AI_MODEL_WRITER", default=""),
    "finance": env.str("AI_MODEL_FINANCE", default=""),
    "deck": env.str("AI_MODEL_DECK", default=""),
    "prototype": env.str("AI_MODEL_PROTOTYPE", default=""),
    "reviewer": env.str("AI_MODEL_REVIEWER", default=""),
    "partner": env.str("AI_MODEL_PARTNER", default=""),
}
AI_BASE_URL = env.str("AI_BASE_URL", default="")  # an OpenAI compatible chat completions API
AI_API_KEY = env.str("AI_API_KEY", default="")
AI_REQUEST_TIMEOUT_SECONDS = env.int("AI_REQUEST_TIMEOUT_SECONDS", default=60)
AI_DAILY_RUN_CEILING = env.int("AI_DAILY_RUN_CEILING", default=400)  # per member, model calls
# Estimated cost per million tokens in minor units, by model (input, output). For usage reports.
AI_PRICE_PER_MILLION_TOKENS: dict[str, tuple[int, int]] = {}
AI_COST_CURRENCY = "USD"
AI_PARTNER_REPLY_TIMEOUT_SECONDS = env.int("AI_PARTNER_REPLY_TIMEOUT_SECONDS", default=10)
RESEARCH_ALLOWED_DOMAINS = env.list("RESEARCH_ALLOWED_DOMAINS", default=[])
RESEARCH_PROVIDER = env.str(
    "RESEARCH_PROVIDER", default="apps.toolkit.ai.research.fake.FakeResearchProvider"
)
RESEARCH_SEARCH_URL = env.str("RESEARCH_SEARCH_URL", default="")
RESEARCH_SEARCH_KEY = env.str("RESEARCH_SEARCH_KEY", default="")
EXPORT_URL_TTL = env.int("EXPORT_URL_TTL", default=900)
EXPORT_RETENTION_DAYS = env.int("EXPORT_RETENTION_DAYS", default=7)
DECK_MAX_SLIDES = env.int("DECK_MAX_SLIDES", default=100)
DECK_MAX_ELEMENTS_PER_SLIDE = 200
DECK_VERSIONS_KEPT = env.int("DECK_VERSIONS_KEPT", default=30)
PLAN_VERSIONS_KEPT = env.int("PLAN_VERSIONS_KEPT", default=20)
TOOLKIT_MAX_ACTIVE_JOBS = env.int("TOOLKIT_MAX_ACTIVE_JOBS", default=4)
PROTOTYPE_MAX_SCREENS = env.int("PROTOTYPE_MAX_SCREENS", default=20)
VENTURE_DELETE_GRACE_DAYS = env.int("VENTURE_DELETE_GRACE_DAYS", default=14)
# Research for one report runs its questions side by side. Tests turn it off (one connection).
TOOLKIT_PARALLEL_RESEARCH = env.bool("TOOLKIT_PARALLEL_RESEARCH", default=True)

# --- Video meetings ----------------------------------------------------------
# One adapter per provider; a mentor picks one, and MEETING_DEFAULT_PROVIDER covers the rest.
MEETING_DEFAULT_PROVIDER = env.str("MEETING_DEFAULT_PROVIDER", default="google_meet")
MEETING_PROVIDERS = {
    "google_meet": env.str(
        "MEETING_GOOGLE_MEET_ADAPTER", default="apps.integrations.meetings.fake.FakeMeetingProvider"
    ),
    "zoom": env.str(
        "MEETING_ZOOM_ADAPTER", default="apps.integrations.meetings.fake.FakeMeetingProvider"
    ),
}
# Google Meet links are made as events on one platform calendar, through an OAuth refresh token.
GOOGLE_MEET_CLIENT_ID = env.str("GOOGLE_MEET_CLIENT_ID", default="")
GOOGLE_MEET_CLIENT_SECRET = env.str("GOOGLE_MEET_CLIENT_SECRET", default="")
GOOGLE_MEET_REFRESH_TOKEN = env.str("GOOGLE_MEET_REFRESH_TOKEN", default="")
GOOGLE_MEET_CALENDAR_ID = env.str("GOOGLE_MEET_CALENDAR_ID", default="primary")
# Zoom meetings are made with a Server-to-Server OAuth app on the platform account.
ZOOM_ACCOUNT_ID = env.str("ZOOM_ACCOUNT_ID", default="")
ZOOM_CLIENT_ID = env.str("ZOOM_CLIENT_ID", default="")
ZOOM_CLIENT_SECRET = env.str("ZOOM_CLIENT_SECRET", default="")
