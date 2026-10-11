from abc import ABC, abstractmethod
from dataclasses import dataclass

QUARANTINE = "quarantine"
MEDIA = "media"
PRIVATE = "private"


class ObjectTooLarge(Exception):
    pass


@dataclass(frozen=True)
class PresignedPost:
    """Everything a client needs to upload one object straight to storage."""

    url: str
    fields: dict[str, str]
    expires_in: int


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    content_type: str


class ObjectStorage(ABC):
    """Object storage with two logical buckets.

    ``quarantine`` takes raw client uploads and is never public. ``media`` holds
    files that were checked and re-encoded, served through a cookieless CDN. ``private`` holds
    checked documents, which are only ever handed out through short lived signed links.
    """

    @abstractmethod
    def presign_post(
        self, *, bucket: str, key: str, content_type: str, max_size: int, expires_in: int
    ) -> PresignedPost:
        """A short lived upload form that storage itself limits by size and type."""

    @abstractmethod
    def head(self, *, bucket: str, key: str) -> ObjectInfo | None:
        """Size and type of an object, or None if it does not exist."""

    @abstractmethod
    def read(self, *, bucket: str, key: str, max_size: int) -> bytes:
        """The object's bytes. Raises ``ObjectTooLarge`` rather than reading past the limit."""

    @abstractmethod
    def write(
        self, *, bucket: str, key: str, data: bytes, content_type: str, cache_control: str = ""
    ) -> None:
        """Store an object, replacing any existing one."""

    @abstractmethod
    def delete(self, *, bucket: str, key: str) -> None:
        """Remove an object. Missing objects are not an error."""

    @abstractmethod
    def presign_get(
        self, *, bucket: str, key: str, expires_in: int, filename: str, content_type: str
    ) -> str:
        """A short lived address for one object that always downloads it as an attachment."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """The CDN address of an object in the media bucket."""
