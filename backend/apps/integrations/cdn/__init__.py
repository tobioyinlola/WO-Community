from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.cdn.base import CachePurger

__all__ = ["CachePurger", "get_cache_purger"]


def get_cache_purger() -> CachePurger:
    """Purger selected by the CDN_PURGER setting (dotted path)."""
    purger: CachePurger = import_string(settings.CDN_PURGER)()
    return purger
