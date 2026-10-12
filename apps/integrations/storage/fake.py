from typing import ClassVar
from urllib.parse import quote

from django.conf import settings

from apps.integrations.storage.base import ObjectInfo, ObjectStorage, ObjectTooLarge, PresignedPost


class UploadRefused(Exception):
    """The fake storage rejected a simulated client upload, as real storage would."""


class FakeStorage(ObjectStorage):
    """In-memory storage for tests and local runs. Nothing leaves the process."""

    objects: ClassVar[dict[tuple[str, str], tuple[bytes, str]]] = {}
    forms: ClassVar[dict[tuple[str, str], dict[str, object]]] = {}
    locked: ClassVar[set[tuple[str, str]]] = set()

    @classmethod
    def reset(cls) -> None:
        cls.objects.clear()
        cls.forms.clear()
        cls.locked.clear()

    # --- what the client would do with the presigned form -----------------------------------

    @classmethod
    def client_upload(cls, post: PresignedPost, data: bytes, content_type: str) -> None:
        """Enforce the form's conditions like real storage, then keep the object."""
        key = post.fields["key"]
        bucket = post.fields["bucket"]
        if content_type != post.fields["Content-Type"]:
            raise UploadRefused("content type does not match the form")
        if len(data) > int(post.fields["x-max-size"]):
            raise UploadRefused("object larger than the form allows")
        cls.objects[(bucket, key)] = (data, content_type)

    # --- the adapter interface -----------------------------------------------------------------

    def presign_post(
        self, *, bucket: str, key: str, content_type: str, max_size: int, expires_in: int
    ) -> PresignedPost:
        fields = {
            "key": key,
            "bucket": bucket,
            "Content-Type": content_type,
            "x-max-size": str(max_size),
        }
        return PresignedPost(f"https://storage.test/{bucket}", fields, expires_in)

    def head(self, *, bucket: str, key: str) -> ObjectInfo | None:
        found = self.objects.get((bucket, key))
        return ObjectInfo(len(found[0]), found[1]) if found else None

    def read(self, *, bucket: str, key: str, max_size: int) -> bytes:
        data, _ = self.objects[(bucket, key)]
        if len(data) > max_size:
            raise ObjectTooLarge(key)
        return data

    def write(
        self, *, bucket: str, key: str, data: bytes, content_type: str, cache_control: str = ""
    ) -> None:
        if (bucket, key) in self.locked:
            raise PermissionError(f"{key} is locked")
        self.objects[(bucket, key)] = (data, content_type)

    def delete(self, *, bucket: str, key: str) -> None:
        if (bucket, key) in self.locked:
            raise PermissionError(f"{key} is locked")
        self.objects.pop((bucket, key), None)

    def write_once(
        self, *, bucket: str, key: str, data: bytes, content_type: str, retain_days: int
    ) -> bool:
        if (bucket, key) in self.objects:
            return False
        self.objects[(bucket, key)] = (data, content_type)
        self.locked.add((bucket, key))
        return True

    def presign_get(
        self, *, bucket: str, key: str, expires_in: int, filename: str, content_type: str
    ) -> str:
        if (bucket, key) not in self.objects:
            raise KeyError(key)
        return (
            f"https://private.test/{bucket}/{key}"
            f"?expires_in={expires_in}&filename={quote(filename)}&type={quote(content_type)}"
        )

    def public_url(self, key: str) -> str:
        return f"{settings.MEDIA_BASE_URL.rstrip('/')}/{key}"
