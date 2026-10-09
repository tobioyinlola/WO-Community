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
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "apps.core",
    "apps.audit",
    "apps.accounts",
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
        "auth_forgot": "5/hour",
        "auth_token": "20/hour",
        "auth_refresh": "60/min",
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
}

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
CELERY_TASK_ROUTES = {"core.dispatch_outbox": {"queue": "critical"}}
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "dispatch-outbox": {"task": "core.dispatch_outbox", "schedule": 5.0},
    "audit-ensure-partitions": {"task": "audit.ensure_partitions", "schedule": 86400.0},
    "audit-verify-chain": {"task": "audit.verify_previous_day", "schedule": 86400.0},
}
OUTBOX_MAX_ATTEMPTS = 8

# --- Adapters ----------------------------------------------------------------
EMAIL_ADAPTER = env.str("EMAIL_ADAPTER", default="apps.integrations.email.fake.FakeEmailAdapter")

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
