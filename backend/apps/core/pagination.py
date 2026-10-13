from rest_framework.pagination import CursorPagination, LimitOffsetPagination


class DefaultCursorPagination(CursorPagination):
    """Cursor pagination for feeds and other lists that can grow large."""

    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100
    ordering = "-created_at"


class AdminLimitOffsetPagination(LimitOffsetPagination):
    """Offset pagination, only for admin tables whose size is bounded."""

    default_limit = 20
    max_limit = 100
