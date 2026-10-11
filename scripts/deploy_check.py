"""Runs ``manage.py check --deploy`` against the production settings with throwaway values.

The check validates configuration (HTTPS, cookies, HSTS and the like), not secrets, so any
environment variable the production settings require is filled with a placeholder unless it is
already set. The real values never need to be on a CI runner.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

# Taken before importing anything that may set defaults of its own.
ORIGINAL_ENV = dict(os.environ)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.fernet import Fernet  # noqa: E402

from config.settings.keys import ephemeral_jwt_keys  # noqa: E402

private, public = ephemeral_jwt_keys()
defaults = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "DJANGO_ALLOWED_HOSTS": "api.example.com",
    "DATABASE_URL": "postgres://wo:wo@localhost:5432/wo",
    "JWT_PRIVATE_KEY": private.replace("\n", "\\n"),
    "JWT_PUBLIC_KEY": public.replace("\n", "\\n"),
    "FIELD_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
    "EMAIL_ADAPTER": "apps.integrations.email.fake.FakeEmailAdapter",
    "STORAGE_ADAPTER": "apps.integrations.storage.s3.S3Storage",
    "MALWARE_SCANNER": "apps.integrations.malware.clamd.ClamdScanner",
    "MEDIA_BASE_URL": "https://media.example.com",
    "MEETING_GOOGLE_MEET_ADAPTER": "apps.integrations.meetings.google.GoogleMeetProvider",
    "GOOGLE_MEET_CLIENT_ID": "id",
    "GOOGLE_MEET_CLIENT_SECRET": "secret",
    "GOOGLE_MEET_REFRESH_TOKEN": "token",
    "AI_PROVIDER": "http",
    "AI_BASE_URL": "https://ai.example.com/v1",
    "AI_API_KEY": "key",
    "RESEARCH_PROVIDER": "apps.toolkit.ai.research.web.WebResearchProvider",
    "RESEARCH_SEARCH_URL": "https://search.example.com/v1/search",
    "RESEARCH_SEARCH_KEY": "key",
    "RESEARCH_ALLOWED_DOMAINS": "data.example.org",
}
env = {**defaults, **ORIGINAL_ENV}
sys.exit(
    subprocess.call(  # noqa: S603  # fixed arguments, our own interpreter
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=ROOT,
        env=env,
    )
)
