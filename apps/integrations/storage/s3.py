"""S3 compatible storage (AWS S3, MinIO, R2 and similar).

Credentials come from the environment or the instance role, never from code.
The quarantine bucket must be private; the media bucket is read through the CDN.
"""

from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import Any
from urllib.parse import quote

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings

from apps.integrations.storage.base import (
    ANCHOR,
    MEDIA,
    PRIVATE,
    QUARANTINE,
    ObjectInfo,
    ObjectStorage,
    ObjectTooLarge,
    PresignedPost,
)


class S3Storage(ObjectStorage):
    @cached_property
    def client(self) -> Any:
        return boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
            region_name=settings.STORAGE_REGION,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.STORAGE_SECRET_ACCESS_KEY or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.STORAGE_ENDPOINT_URL else "auto"},
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3},
            ),
        )

    @staticmethod
    def bucket_name(bucket: str) -> str:
        names = {
            QUARANTINE: settings.STORAGE_QUARANTINE_BUCKET,
            MEDIA: settings.STORAGE_MEDIA_BUCKET,
            PRIVATE: settings.STORAGE_PRIVATE_BUCKET,
            ANCHOR: settings.STORAGE_ANCHOR_BUCKET,
        }
        return names[bucket]

    def presign_post(
        self, *, bucket: str, key: str, content_type: str, max_size: int, expires_in: int
    ) -> PresignedPost:
        form = self.client.generate_presigned_post(
            Bucket=self.bucket_name(bucket),
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_size],
            ],
            ExpiresIn=expires_in,
        )
        return PresignedPost(form["url"], dict(form["fields"]), expires_in)

    def head(self, *, bucket: str, key: str) -> ObjectInfo | None:
        try:
            found = self.client.head_object(Bucket=self.bucket_name(bucket), Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectInfo(int(found["ContentLength"]), str(found.get("ContentType", "")))

    def read(self, *, bucket: str, key: str, max_size: int) -> bytes:
        response = self.client.get_object(Bucket=self.bucket_name(bucket), Key=key)
        data: bytes = response["Body"].read(max_size + 1)
        if len(data) > max_size:
            raise ObjectTooLarge(key)
        return data

    def write(
        self, *, bucket: str, key: str, data: bytes, content_type: str, cache_control: str = ""
    ) -> None:
        extra: dict[str, str] = {"CacheControl": cache_control} if cache_control else {}
        self.client.put_object(
            Bucket=self.bucket_name(bucket),
            Key=key,
            Body=data,
            ContentType=content_type,
            ContentDisposition="attachment" if bucket == PRIVATE else "inline",
            **extra,
        )

    def delete(self, *, bucket: str, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket_name(bucket), Key=key)

    def write_once(
        self, *, bucket: str, key: str, data: bytes, content_type: str, retain_days: int
    ) -> bool:
        """Needs a bucket created with S3 Object Lock; COMPLIANCE mode lets nobody shorten it."""
        if self.head(bucket=bucket, key=key) is not None:
            return False
        self.client.put_object(
            Bucket=self.bucket_name(bucket),
            Key=key,
            Body=data,
            ContentType=content_type,
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=datetime.now(UTC) + timedelta(days=retain_days),
        )
        return True

    def presign_get(
        self, *, bucket: str, key: str, expires_in: int, filename: str, content_type: str
    ) -> str:
        safe = "".join(c for c in filename if c.isprintable() and c not in '"\\/;')[:150]
        ascii_name = safe.encode("ascii", "replace").decode().replace("?", "_") or "download"
        disposition = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(safe or "download")}'
        )
        url: str = self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name(bucket),
                "Key": key,
                "ResponseContentDisposition": disposition,
                "ResponseContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url

    def public_url(self, key: str) -> str:
        return f"{settings.MEDIA_BASE_URL.rstrip('/')}/{key}"
