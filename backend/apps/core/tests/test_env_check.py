"""The production environment check reports every problem at once, naming each variable."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

from config.env_check import check, enforce, render
from config.settings.keys import ephemeral_jwt_keys

ROOT = Path(__file__).resolve().parents[3]
_PRIVATE, _PUBLIC = ephemeral_jwt_keys()
TOOLS = ("SCORE", "PLAN", "FORECAST", "DECKS", "PROTOTYPES", "PARTNER")

COMPLETE = {
    "DJANGO_SECRET_KEY": "Xk3-" * 4 + "q9Zp7Lw2Rt8Vb5Nc1Mh6Jd4Gf0Sa" * 2,
    "DJANGO_ALLOWED_HOSTS": "api.example.com",
    "DATABASE_URL": "postgres://u:p@db.example.com:5432/app",
    "REDIS_URL": "redis://default:p@redis.example.com:6379",
    "CORS_ALLOWED_ORIGINS": "https://app.example.com",
    "FRONTEND_URL": "https://app.example.com",
    "API_BASE_URL": "https://api.example.com",
    "NUM_PROXIES": "1",
    "JWT_PRIVATE_KEY": _PRIVATE.replace("\n", "\\n"),
    "JWT_PUBLIC_KEY": _PUBLIC.replace("\n", "\\n"),
    "FIELD_ENCRYPTION_KEYS": Fernet.generate_key().decode(),
    "EMAIL_ADAPTER": "apps.integrations.email.resend.ResendEmailAdapter",
    "RESEND_API_KEY": "re_test",
    "RESEND_WEBHOOK_SECRET": "whsec_test",
    "EMAIL_FROM_TRANSACTIONAL": "WO Community <no-reply@mail.example.com>",
    "EMAIL_FROM_MARKETING": "WO Community <community@news.example.com>",
    "STORAGE_ADAPTER": "apps.integrations.storage.s3.S3Storage",
    "STORAGE_ACCESS_KEY_ID": "id",
    "STORAGE_SECRET_ACCESS_KEY": "secret",
    "MALWARE_SCANNER": "apps.integrations.malware.clamd.ClamdScanner",
    "MEDIA_BASE_URL": "https://media.example.com",
    "MEETING_GOOGLE_MEET_ADAPTER": "apps.integrations.meetings.google.GoogleMeetProvider",
    "GOOGLE_MEET_CLIENT_ID": "a",
    "GOOGLE_MEET_CLIENT_SECRET": "b",
    "GOOGLE_MEET_REFRESH_TOKEN": "c",
    "AI_PROVIDER": "http",
    "AI_BASE_URL": "https://ai.example.com/v1",
    "AI_API_KEY": "key",
    "RESEARCH_PROVIDER": "apps.toolkit.ai.research.web.WebResearchProvider",
    "RESEARCH_ALLOWED_DOMAINS": "data.example.org",
    "CDN_PURGER": "apps.integrations.cdn.cloudflare.CloudflarePurger",
    "CLOUDFLARE_API_TOKEN": "t",
    "CLOUDFLARE_ZONE_ID": "z",
    "CDN_ORIGIN_URL": "https://api.example.com",
}


def report(**changes: str | None):
    values = {**COMPLETE}
    for key, value in changes.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = value
    return check(lambda name: values.get(name, ""))


def named(result) -> set[str]:
    return {finding.name for finding in result.problems}


def test_a_complete_environment_has_no_problems_and_no_warnings():
    result = report()
    assert result.ok
    assert result.warnings == []
    assert "All required production variables are set" in render(result)


def test_every_missing_variable_is_reported_together_not_one_at_a_time():
    names = (
        "CORS_ALLOWED_ORIGINS",
        "FRONTEND_URL",
        "API_BASE_URL",
        "JWT_PRIVATE_KEY",
        "EMAIL_ADAPTER",
    )
    result = report(**dict.fromkeys(names))
    assert set(names) <= named(result)
    text = render(result)
    assert "5 problems" in text
    for name in names:
        assert name in text
    assert "Hint:" in text


def test_an_empty_environment_lists_all_the_required_variables():
    result = check(lambda name: "")
    for name in (
        "DJANGO_SECRET_KEY",
        "DJANGO_ALLOWED_HOSTS",
        "DATABASE_URL",
        "REDIS_URL",
        "CORS_ALLOWED_ORIGINS",
        "FRONTEND_URL",
        "API_BASE_URL",
        "NUM_PROXIES",
        "JWT_PRIVATE_KEY",
        "JWT_PUBLIC_KEY",
        "EMAIL_ADAPTER",
        "FIELD_ENCRYPTION_KEYS",
        "STORAGE_ADAPTER",
        "MALWARE_SCANNER",
        "MEDIA_BASE_URL",
        "MEETING_GOOGLE_MEET_ADAPTER",
        "AI_PROVIDER",
        "RESEARCH_PROVIDER",
    ):
        assert name in named(result), name


@pytest.mark.parametrize(
    ("changes", "name", "words"),
    [
        ({"DJANGO_ALLOWED_HOSTS": "*"}, "DJANGO_ALLOWED_HOSTS", "never '*'"),
        ({"DJANGO_ALLOWED_HOSTS": "https://api.example.com"}, "DJANGO_ALLOWED_HOSTS", "host names"),
        ({"DJANGO_SECRET_KEY": "change-me-please"}, "DJANGO_SECRET_KEY", "placeholder"),
        ({"DATABASE_URL": "mysql://u:p@h/db"}, "DATABASE_URL", "PostgreSQL"),
        ({"REDIS_URL": "http://redis"}, "REDIS_URL", "Redis"),
        ({"CORS_ALLOWED_ORIGINS": "http://app.example.com"}, "CORS_ALLOWED_ORIGINS", "https"),
        ({"CORS_ALLOWED_ORIGINS": "https://app.example.com/x"}, "CORS_ALLOWED_ORIGINS", "no path"),
        ({"FRONTEND_URL": "http://localhost:5173"}, "FRONTEND_URL", "https"),
        ({"API_BASE_URL": "https://localhost"}, "API_BASE_URL", "https"),
        ({"MEDIA_BASE_URL": "http://media.example.com"}, "MEDIA_BASE_URL", "https"),
        ({"NUM_PROXIES": "0"}, "NUM_PROXIES", "at least 1"),
        ({"NUM_PROXIES": "one"}, "NUM_PROXIES", "at least 1"),
        ({"DEBUG": "true"}, "DEBUG", "false"),
        ({"REFRESH_COOKIE_SECURE": "false"}, "REFRESH_COOKIE_SECURE", "true"),
        ({"JWT_PRIVATE_KEY": "not a key"}, "JWT_PRIVATE_KEY", "PEM"),
        ({"JWT_PUBLIC_KEY": "not a key"}, "JWT_PUBLIC_KEY", "PEM"),
        ({"FIELD_ENCRYPTION_KEYS": "short"}, "FIELD_ENCRYPTION_KEYS", "Fernet"),
        (
            {"EMAIL_ADAPTER": "apps.integrations.email.nope.Adapter"},
            "EMAIL_ADAPTER",
            "known adapters",
        ),
        ({"RESEND_API_KEY": None}, "RESEND_API_KEY", "required"),
        ({"RESEND_WEBHOOK_SECRET": None}, "RESEND_WEBHOOK_SECRET", "required"),
        ({"EMAIL_FROM_TRANSACTIONAL": None}, "EMAIL_FROM_TRANSACTIONAL", "required"),
        ({"EMAIL_FROM_MARKETING": "community"}, "EMAIL_FROM_MARKETING", "email address"),
        ({"STORAGE_SECRET_ACCESS_KEY": None}, "STORAGE_SECRET_ACCESS_KEY", "required"),
        ({"STORAGE_UPLOAD_METHOD": "form"}, "STORAGE_UPLOAD_METHOD", "'post' or 'put'"),
        ({"MEETING_GOOGLE_MEET_ADAPTER": None}, "MEETING_GOOGLE_MEET_ADAPTER", "fake"),
        ({"GOOGLE_MEET_REFRESH_TOKEN": None}, "GOOGLE_MEET_REFRESH_TOKEN", "required"),
        ({"AI_PROVIDER": "fake"}, "AI_PROVIDER", "real provider"),
        ({"AI_API_KEY": None}, "AI_API_KEY", "required"),
        ({"RESEARCH_ALLOWED_DOMAINS": ""}, "RESEARCH_ALLOWED_DOMAINS", "sites"),
        ({"CLOUDFLARE_ZONE_ID": None}, "CLOUDFLARE_ZONE_ID", "required"),
    ],
)
def test_each_wrong_value_names_its_variable(changes, name, words):
    result = report(**changes)
    matching = [f for f in result.problems if f.name == name]
    assert matching, f"{name} not reported: {render(result)}"
    assert any(words in f.problem for f in matching), render(result)


def test_the_public_key_must_belong_to_the_private_key():
    _, other_public = ephemeral_jwt_keys()
    result = report(JWT_PUBLIC_KEY=other_public.replace("\n", "\\n"))
    assert "JWT_PUBLIC_KEY" in named(result)
    assert "public half" in render(result)


def test_keys_may_also_be_written_with_real_line_breaks():
    assert report(JWT_PRIVATE_KEY=_PRIVATE, JWT_PUBLIC_KEY=_PUBLIC).ok


def test_the_fake_email_adapter_starts_but_warns_that_nothing_is_sent():
    fake = "apps.integrations.email.fake.FakeEmailAdapter"
    result = report(EMAIL_ADAPTER=fake)
    assert result.ok
    assert any(
        w.name == "EMAIL_ADAPTER" and "no email is sent" in w.problem for w in result.warnings
    )
    # The Resend variables are not needed with the fake adapter.
    assert report(EMAIL_ADAPTER=fake, RESEND_API_KEY=None, RESEND_WEBHOOK_SECRET=None).ok


def test_toolkit_settings_are_not_needed_when_every_tool_is_switched_off():
    off = {f"TOOLKIT_FEATURE_{tool}": "false" for tool in TOOLS}
    result = report(AI_PROVIDER=None, RESEARCH_PROVIDER=None, **off)
    assert result.ok, render(result)


def test_the_local_run_switch_relaxes_only_the_https_checks():
    values = {**COMPLETE, "LOCAL_PRODUCTION_RUN": "true", "FRONTEND_URL": "http://localhost:4173"}
    assert check(lambda name: values.get(name, "")).ok
    values["NUM_PROXIES"] = "0"
    assert "NUM_PROXIES" in named(check(lambda name: values.get(name, "")))


def test_a_short_secret_key_is_a_warning_not_a_stop():
    result = report(DJANGO_SECRET_KEY="short-but-unique-1234")
    assert result.ok
    assert any(w.name == "DJANGO_SECRET_KEY" for w in result.warnings)


def test_secrets_are_never_printed_in_the_report():
    secret = "super-secret-value-123"  # noqa: S105 - a made up value
    result = report(
        RESEND_API_KEY=secret,
        STORAGE_SECRET_ACCESS_KEY=secret,
        JWT_PRIVATE_KEY=secret,
        AI_API_KEY=None,
    )
    assert secret not in render(result)


def test_enforce_raises_one_error_that_lists_everything():
    with pytest.raises(ImproperlyConfigured) as raised:
        enforce(lambda name: "")
    message = str(raised.value)
    assert "DJANGO_SECRET_KEY" in message
    assert "EMAIL_ADAPTER" in message
    assert "JWT_PRIVATE_KEY" in message


def test_the_command_prints_the_report_and_fails_when_something_is_missing(monkeypatch, capsys):
    for name, value in COMPLETE.items():
        monkeypatch.setenv(name, value)
    call_command("check_env")
    assert "All required production variables are set" in capsys.readouterr().out
    monkeypatch.delenv("EMAIL_ADAPTER")
    monkeypatch.delenv("API_BASE_URL")
    with pytest.raises(CommandError):
        call_command("check_env")
    out = capsys.readouterr().out
    assert "EMAIL_ADAPTER" in out
    assert "API_BASE_URL" in out


def test_manage_py_check_env_runs_without_loading_any_settings():
    # An empty environment would stop the production settings; the command must still answer.
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "SYSTEMROOT", "TEMP", "TMP"}}
    env["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    result = subprocess.run(  # noqa: S603
        [sys.executable, "manage.py", "check_env"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 1
    assert "DJANGO_SECRET_KEY" in result.stdout
    assert "JWT_PRIVATE_KEY" in result.stdout
    assert "Traceback" not in result.stderr


def test_the_secrets_script_prints_values_the_check_accepts():
    result = subprocess.run(  # noqa: S603
        [sys.executable, "scripts/generate_secrets.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    values = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert set(values) == {
        "DJANGO_SECRET_KEY",
        "FIELD_ENCRYPTION_KEYS",
        "JWT_PRIVATE_KEY",
        "JWT_PUBLIC_KEY",
    }
    # One line each, with a written \n between the lines of a key, as Railway needs.
    assert "\\n" in values["JWT_PRIVATE_KEY"]
    checked = check(lambda name: values.get(name, ""))
    assert not [f for f in checked.problems if f.name in values]
    assert not [f for f in checked.warnings if f.name in values]
