"""Have I Been Pwned range lookup (k-anonymity).

Only the first five characters of the password's SHA-1 leave the process, and
the response is padded so its size reveals nothing. The password itself and
its full hash are never sent.
"""

import hashlib
from urllib.error import URLError
from urllib.request import Request, urlopen

import structlog

from apps.integrations.passwords.base import BreachChecker

logger = structlog.get_logger(__name__)

RANGE_URL = "https://api.pwnedpasswords.com/range/"
TIMEOUT_SECONDS = 2.0


class HibpBreachChecker(BreachChecker):
    def is_breached(self, password: str) -> bool:
        digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        request = Request(  # noqa: S310  # nosec B310
            RANGE_URL + prefix,
            headers={"Add-Padding": "true", "User-Agent": "wo-community-backend"},
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310  # nosec B310
                body = response.read().decode("ascii", errors="ignore")
        except (URLError, TimeoutError, OSError):
            logger.warning("breach_lookup_unavailable")
            return False
        return _suffix_listed(body, suffix)


def _suffix_listed(body: str, suffix: str) -> bool:
    for line in body.splitlines():
        candidate, _, count = line.partition(":")
        if candidate.strip().upper() == suffix and count.strip().isdigit() and int(count) > 0:
            return True
    return False
