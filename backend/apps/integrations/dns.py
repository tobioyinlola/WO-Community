"""Looking up DNS text records, for the email health check.

Behind a small class so tests can answer without touching the network.
"""

from typing import Protocol

import dns.exception
import dns.resolver


class Resolver(Protocol):
    def txt(self, name: str) -> list[str] | None:
        """TXT strings at ``name``: [] if none, None if the lookup itself failed."""


class SystemResolver:
    def __init__(self, timeout: float = 3.0) -> None:
        self.timeout = timeout

    def txt(self, name: str) -> list[str] | None:
        try:
            answer = dns.resolver.resolve(name, "TXT", lifetime=self.timeout)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except dns.exception.DNSException:
            return None
        return ["".join(part.decode() for part in record.strings) for record in answer]
