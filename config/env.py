"""Environment access with fail-fast validation.

Every setting that varies per environment is read here so a missing or
malformed value stops the process at start up instead of at first use.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file))


def require(name: str) -> str:
    value = env.str(name, default="")
    if not value:
        raise ImproperlyConfigured(f"Environment variable {name} is required")
    return value
