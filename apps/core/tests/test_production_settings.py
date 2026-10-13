"""The production settings refuse to start when something needed is missing or unsafe."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

GOOD = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "SECRET_KEY": "x" * 50,
    "DJANGO_ALLOWED_HOSTS": "api.example.com",
    "DATABASE_URL": "postgres://u:p@db.example.com:5432/app",
    "REDIS_URL": "redis://default:p@redis.example.com:6379",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
    "FRONTEND_URL": "https://app.example.com",
    "API_BASE_URL": "https://api.example.com",
    "NUM_PROXIES": "1",
    "JWT_PRIVATE_KEY": "private\nkey",
    "JWT_PUBLIC_KEY": "public\nkey",
    "EMAIL_ADAPTER": "apps.integrations.email.fake.FakeEmailAdapter",
    "FIELD_ENCRYPTION_KEYS": "k",
    "STORAGE_ADAPTER": "apps.integrations.storage.s3.S3Storage",
    "MALWARE_SCANNER": "apps.integrations.malware.clamd.ClamdScanner",
    "MEDIA_BASE_URL": "https://media.example.com",
    "MEETING_DEFAULT_PROVIDER": "google_meet",
    "GOOGLE_MEET_CLIENT_ID": "a",
    "GOOGLE_MEET_CLIENT_SECRET": "b",
    "GOOGLE_MEET_REFRESH_TOKEN": "c",
    **{
        f"TOOLKIT_FEATURE_{n}": "false"
        for n in ("SCORE", "PLAN", "FORECAST", "DECKS", "PROTOTYPES", "PARTNER")
    },
    "MEETING_GOOGLE_MEET_ADAPTER": "apps.integrations.meetings.google.GoogleMeetProvider",
}


def start(**changes: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "TEMP", "TMP"}}
    env.update(GOOD)
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings.production as s; print('started')"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_a_complete_environment_starts():
    result = start()
    assert result.returncode == 0, result.stderr[-600:]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"SECRET_KEY": None}, "DJANGO_SECRET_KEY"),
        ({"DJANGO_ALLOWED_HOSTS": None}, "DJANGO_ALLOWED_HOSTS"),
        ({"DJANGO_ALLOWED_HOSTS": "*"}, "never '*'"),
        ({"DATABASE_URL": None}, "DATABASE_URL"),
        ({"REDIS_URL": None}, "REDIS_URL"),
        ({"CORS_ALLOWED_ORIGINS": None}, "CORS_ALLOWED_ORIGINS"),
        ({"CORS_ALLOWED_ORIGINS": "http://app.example.com"}, "https"),
        ({"FRONTEND_URL": "http://localhost:5173"}, "FRONTEND_URL"),
        ({"API_BASE_URL": "http://localhost:8000"}, "API_BASE_URL"),
        ({"NUM_PROXIES": "0"}, "NUM_PROXIES"),
        ({"DEBUG": "true"}, "DEBUG"),
        ({"JWT_PRIVATE_KEY": None}, "JWT_PRIVATE_KEY"),
    ],
)
def test_a_missing_or_unsafe_setting_stops_the_start_with_its_name(changes, message):
    result = start(**changes)
    assert result.returncode != 0
    assert message in result.stderr
