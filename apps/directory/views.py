from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.public import PublicView
from apps.directory import selectors
from apps.directory.serializers import (
    FounderDetailSerializer,
    FounderPageSerializer,
    FounderQuerySerializer,
    SitemapQuerySerializer,
    SitemapSerializer,
    StartupDetailSerializer,
    StartupPageSerializer,
    StartupQuerySerializer,
    clean_query,
    founder_page,
    startup_page,
)

SITEMAP_CACHE_CONTROL = "public, max-age=3600, stale-while-revalidate=3600"


ERRORS = {
    400: OpenApiResponse(description="Invalid filter or cursor"),
    429: OpenApiResponse(description="Too many requests"),
}


class StartupListView(PublicView):
    @extend_schema(
        operation_id="public_startups_list",
        summary="Browse and search the startup directory",
        description="Listed startups only, with what their owners made public. Featured startups "
        "come first. Without `q` results are paged by `cursor`; with `q` you get the best "
        "matches only (no cursor), so refine the search instead of paging.",
        parameters=[StartupQuerySerializer],
        responses={200: StartupPageSerializer, **ERRORS},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        params = clean_query(StartupQuerySerializer, request.query_params.dict())
        results, next_cursor = selectors.search_startups(**params)
        return self.cached(request, startup_page(results, next_cursor))


class StartupDetailView(PublicView):
    @extend_schema(
        operation_id="public_startup_detail",
        summary="One listed startup",
        responses={200: StartupDetailSerializer, 404: OpenApiResponse(description="Not listed")},
        tags=["public"],
    )
    def get(self, request: Request, slug: str) -> Response:
        data = selectors.startup_detail(slug)
        if data is None:
            raise exceptions.NotFound()
        return self.cached(request, StartupDetailSerializer(data).data)


class FounderListView(PublicView):
    @extend_schema(
        operation_id="public_founders_list",
        summary="Browse and search founders who made their profile public",
        parameters=[FounderQuerySerializer],
        responses={200: FounderPageSerializer, **ERRORS},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        params = clean_query(FounderQuerySerializer, request.query_params.dict())
        results, next_cursor = selectors.search_founders(**params)
        return self.cached(request, founder_page(results, next_cursor))


class FounderDetailView(PublicView):
    @extend_schema(
        operation_id="public_founder_detail",
        summary="One public founder page",
        description="Shows only the field groups the founder made public.",
        responses={200: FounderDetailSerializer, 404: OpenApiResponse(description="Not public")},
        tags=["public"],
    )
    def get(self, request: Request, slug: str) -> Response:
        data = selectors.founder_detail(slug)
        if data is None:
            raise exceptions.NotFound()
        return self.cached(request, FounderDetailSerializer(data).data)


class SitemapView(PublicView):
    cache_control = SITEMAP_CACHE_CONTROL

    @extend_schema(
        summary="Every public page with its last change",
        description="For search engines: the front end turns this into sitemap.xml.",
        responses={200: SitemapSerializer},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        clean_query(SitemapQuerySerializer, request.query_params.dict())  # rejects stray params
        return self.cached(request, SitemapSerializer(selectors.sitemap()).data)
