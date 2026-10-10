from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.core.public import PublicView
from apps.editorial import selectors, services
from apps.editorial.serializers import (
    BannerSerializer,
    CommentWriteSerializer,
    EditorialItemPageSerializer,
    EditorialItemSerializer,
    EditorialPageQuerySerializer,
    EditorialQuerySerializer,
    ItemCommentPageSerializer,
    ItemCommentSerializer,
    ItemReactionResultSerializer,
    ItemReactionSerializer,
    PublicItemSerializer,
    PublicPageSerializer,
    WinCreateSerializer,
    WinPageSerializer,
    WinSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member"),
    404: OpenApiResponse(description="Not found, or not published"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _params(request: Request, serializer_class: Any) -> dict[str, Any]:
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class EditorialListView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="editorial_list",
        summary="News, awards, celebrations and more",
        description="Published items, newest first. Filter by `type`.",
        parameters=[EditorialQuerySerializer],
        responses={200: EditorialItemPageSerializer, **ERRORS},
        tags=["editorial"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.feed(request.user, **_params(request, EditorialQuerySerializer))
        return _private(Response(EditorialItemPageSerializer(page).data))


class EditorialItemView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One published item",
        responses={200: EditorialItemSerializer, **ERRORS},
        tags=["editorial"],
    )
    def get(self, request: Request, item_id: UUID) -> Response:
        _, view = selectors.get_item(request.user, item_id)
        return _private(Response(EditorialItemSerializer(view).data))


class BannersView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Announcements pinned as a banner on the member home right now",
        responses={200: BannerSerializer(many=True), **ERRORS},
        tags=["editorial"],
    )
    def get(self, request: Request) -> Response:
        return _private(Response(BannerSerializer(selectors.banners(), many=True).data))


class ItemCommentsView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="editorial_comments_list",
        summary="Comments on an item, oldest first",
        parameters=[EditorialPageQuerySerializer],
        responses={200: ItemCommentPageSerializer, **ERRORS},
        tags=["editorial"],
    )
    def get(self, request: Request, item_id: UUID) -> Response:
        page = selectors.comments(
            request.user, item_id, **_params(request, EditorialPageQuerySerializer)
        )
        return _private(Response(ItemCommentPageSerializer(page).data))

    @extend_schema(
        summary="Comment on an item",
        description="Refused with 409 when the item's comments are switched off. Limited per "
        "member per day.",
        request=CommentWriteSerializer,
        responses={
            201: ItemCommentSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Comments are off"),
            429: OpenApiResponse(description="Daily limit"),
        },
        tags=["editorial"],
    )
    def post(self, request: Request, item_id: UUID) -> Response:
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = services.add_comment(
            user_id=_uid(request), item_id=item_id, body=serializer.validated_data["body"]
        )
        view = selectors.get_comment(request.user, comment.pk)
        return Response(ItemCommentSerializer(view).data, status=status.HTTP_201_CREATED)


class ItemCommentView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Edit your comment",
        request=CommentWriteSerializer,
        responses={200: ItemCommentSerializer, **ERRORS},
        tags=["editorial"],
    )
    def patch(self, request: Request, comment_id: UUID) -> Response:
        serializer = CommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_comment(
            user_id=_uid(request), comment_id=comment_id, body=serializer.validated_data["body"]
        )
        return Response(ItemCommentSerializer(selectors.get_comment(request.user, comment_id)).data)

    @extend_schema(
        summary="Delete your comment", responses={204: None, **ERRORS}, tags=["editorial"]
    )
    def delete(self, request: Request, comment_id: UUID) -> Response:
        services.delete_comment(user_id=_uid(request), comment_id=comment_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _reaction_result(request: Request, item_id: UUID, created: bool) -> Response:
    _, view = selectors.get_item(request.user, item_id)
    body = {
        "created": created,
        "reactions": view["reactions"],
        "reaction_count": view["reaction_count"],
    }
    return Response(ItemReactionResultSerializer(body).data, status=201 if created else 200)


class ItemReactionsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="React to an item",
        description="Idempotent: the same reaction twice leaves one (200).",
        request=ItemReactionSerializer,
        responses={201: ItemReactionResultSerializer, 200: ItemReactionResultSerializer, **ERRORS},
        tags=["editorial"],
    )
    def post(self, request: Request, item_id: UUID) -> Response:
        serializer = ItemReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.react(
            user_id=_uid(request), item_id=item_id, kind=serializer.validated_data["kind"]
        )
        return _reaction_result(request, item_id, created)


class ItemReactionDeleteView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Take a reaction back",
        responses={200: ItemReactionResultSerializer, **ERRORS},
        tags=["editorial"],
    )
    def delete(self, request: Request, item_id: UUID, kind: str) -> Response:
        services.unreact(user_id=_uid(request), item_id=item_id, kind=kind)
        return _reaction_result(request, item_id, False)


class WinSubmissionsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Submit a win for the team to review",
        description="An award, funding round or partnership, with a link to evidence. Up to 3 "
        "waiting at once and 5 a day. You are told when it is reviewed.",
        request=WinCreateSerializer,
        responses={201: WinSerializer, **ERRORS, 429: OpenApiResponse(description="Daily limit")},
        tags=["editorial"],
    )
    def post(self, request: Request) -> Response:
        serializer = WinCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        win = services.submit_win(user_id=_uid(request), data=dict(serializer.validated_data))
        return Response(WinSerializer(selectors.win_view(win)).data, status=201)

    @extend_schema(
        summary="Your win submissions",
        parameters=[EditorialPageQuerySerializer],
        responses={200: WinPageSerializer, **ERRORS},
        tags=["editorial"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.my_wins(_uid(request), **_params(request, EditorialPageQuerySerializer))
        return _private(Response(WinPageSerializer(page).data))


# --- public ---


class PublicNewsView(PublicView):
    @extend_schema(
        operation_id="public_news_list",
        summary="Latest public news for the website",
        parameters=[EditorialQuerySerializer],
        responses={200: PublicPageSerializer, 400: OpenApiResponse(description="Bad filter")},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.public_feed(**_params(request, EditorialQuerySerializer))
        return self.cached(request, PublicPageSerializer(page).data)


class PublicNewsItemView(PublicView):
    @extend_schema(
        summary="One public news item, with Open Graph data",
        responses={200: PublicItemSerializer, 404: OpenApiResponse(description="Not found")},
        tags=["public"],
    )
    def get(self, request: Request, slug: str) -> Response:
        return self.cached(request, PublicItemSerializer(selectors.public_detail(slug)).data)
