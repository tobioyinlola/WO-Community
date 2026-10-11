from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.calendars.base import FeedReader, FeedRejected, FeedUnavailable

__all__ = ["FeedReader", "FeedRejected", "FeedUnavailable", "get_feed_reader"]


def get_feed_reader() -> FeedReader:
    """Reader selected by the CALENDAR_FEED_READER setting (dotted path)."""
    reader: FeedReader = import_string(settings.CALENDAR_FEED_READER)()
    return reader
