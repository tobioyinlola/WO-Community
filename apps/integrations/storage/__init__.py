from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.storage.base import (
    MEDIA,
    QUARANTINE,
    ObjectInfo,
    ObjectStorage,
    ObjectTooLarge,
    PresignedPost,
)

__all__ = [
    "MEDIA",
    "QUARANTINE",
    "ObjectInfo",
    "ObjectStorage",
    "ObjectTooLarge",
    "PresignedPost",
    "get_storage",
]


def get_storage() -> ObjectStorage:
    """Storage selected by the STORAGE_ADAPTER setting (dotted path)."""
    storage: ObjectStorage = import_string(settings.STORAGE_ADAPTER)()
    return storage
