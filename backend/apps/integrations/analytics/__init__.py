from django.conf import settings
from django.utils.module_loading import import_string

from apps.integrations.analytics.base import AnalyticsSink

__all__ = ["AnalyticsSink", "get_sink"]


def get_sink() -> AnalyticsSink:
    """Sink selected by the ANALYTICS_SINK setting (dotted path)."""
    sink: AnalyticsSink = import_string(settings.ANALYTICS_SINK)()
    return sink
