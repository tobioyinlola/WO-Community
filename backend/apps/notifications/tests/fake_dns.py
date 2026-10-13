"""A resolver that answers from a dictionary, so tests never touch the network."""

from typing import ClassVar


class FakeResolver:
    records: ClassVar[dict[str, list[str] | None]] = {}

    def txt(self, name: str) -> list[str] | None:
        return self.records.get(name, [])
