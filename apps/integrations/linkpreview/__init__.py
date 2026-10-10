from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.linkpreview.base import FetchFailed, FetchRejected, Preview, PreviewFetcher

__all__ = ["FetchFailed", "FetchRejected", "Preview", "PreviewFetcher", "get_fetcher"]


def get_fetcher() -> PreviewFetcher:
    """Fetcher selected by the LINK_PREVIEW_FETCHER setting (dotted path)."""
    fetcher: PreviewFetcher = import_string(settings.LINK_PREVIEW_FETCHER)()
    return fetcher
