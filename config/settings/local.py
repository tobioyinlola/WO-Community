import os

os.environ.setdefault("DJANGO_SECRET_KEY", "local-development-key-not-for-production")
os.environ.setdefault("DATABASE_URL", "postgres://wo:wo@localhost:5433/wo")

from .base import *  # noqa: E402,F403
from .base import JWT_PRIVATE_KEY, JWT_PUBLIC_KEY  # noqa: E402
from .keys import ephemeral_jwt_keys  # noqa: E402

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

# Fresh keys on every start invalidate old tokens, which is fine for development.
if not JWT_PRIVATE_KEY:
    JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = ephemeral_jwt_keys()

REFRESH_COOKIE_SECURE = False
