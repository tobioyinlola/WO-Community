from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core import etag, policies
from apps.feed import follows, moderation, selectors, services
from apps.feed.serializers import (
    CommentCreateSerializer,
    CommentListSerializer,
    CommentQuerySerializer,
    CommentSerializer,
    CommentUpdateSerializer,
    FeedQuerySerializer,
    FeedSerializer,
    FollowingListSerializer,
    FollowingQuerySerializer,
    FollowResultSerializer,
    FollowSerializer,
    PostCreateSerializer,
    PostSerializer,
    PostUpdateSerializer,
    ReactionResultSerializer,
    ReactionSerializer,
    ReportCreateSerializer,
    ReportReceivedSerializer,
)

IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member"),
    404: OpenApiResponse(description="Not found, or not visible to you"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _require(request: Request, code: str) -> None:
    if not policies.has_permission(code)(request.user, None):
        raise exceptions.PermissionDenied()


class FeedView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "feed_read"

    @extend_schema(
        operation_id="feed_list",
        summary="The community feed",
        description="Newest or most engaged first, filtered by category and country. "
        "`scope=mine` lists your own posts, including any a moderator hid. Pinned posts come "
        "separately on the first page of the shared feed.",
        parameters=[FeedQuerySerializer],
        responses={200: FeedSerializer, **ERRORS},
        tags=["feed"],
    )
    def get(self, request: Request) -> Response:
        params = FeedQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = selectors.feed(request.user, **params.validated_data)
        response = Response(FeedSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        summary="Write a post",
        description="Rich text is cleaned on the server. Images are finished uploads with "
        "purpose `post_image` (up to 10). `startup_id` posts for a startup you belong to. "
        "Mentioned members are told. Limited per member per day.",
        request=PostCreateSerializer,
        responses={201: PostSerializer, **ERRORS, 429: OpenApiResponse(description="Daily limit")},
        tags=["feed"],
    )
    def post(self, request: Request) -> Response:
        _require(request, "feed.post")
        serializer = PostCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        post = services.create_post(
            user_id=_uid(request),
            category=data["category"],
            body=data["body"],
            images=data["images"],
            startup_id=data["startup_id"],
            mentions=data["mentions"],
        )
        _, view = selectors.get_post(request.user, post.pk)
        return etag.add_etag(Response(PostSerializer(view).data, status=201), post)


class PostView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One post",
        responses={200: PostSerializer, **ERRORS},
        tags=["feed"],
    )
    def get(self, request: Request, post_id: UUID) -> Response:
        post, view = selectors.get_post(request.user, post_id)
        return etag.add_etag(Response(PostSerializer(view).data), post)

    @extend_schema(
        summary="Edit your post",
        description="Send only what changes. `images` replaces the whole list: keep an image by "
        "its `image_id`, add one with `upload_id`. Send the ETag in If-Match.",
        parameters=[IF_MATCH],
        request=PostUpdateSerializer,
        responses={
            200: PostSerializer,
            **ERRORS,
            412: OpenApiResponse(description="The post changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["feed"],
    )
    def patch(self, request: Request, post_id: UUID) -> Response:
        serializer = PostUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = services.update_post(
            user_id=_uid(request),
            post_id=post_id,
            if_match=request.headers.get("If-Match"),
            changes=dict(serializer.validated_data),
        )
        _, view = selectors.get_post(request.user, post.pk)
        return etag.add_etag(Response(PostSerializer(view).data), post)

    @extend_schema(
        summary="Delete your post",
        responses={204: None, **ERRORS},
        tags=["feed"],
    )
    def delete(self, request: Request, post_id: UUID) -> Response:
        services.delete_post(user_id=_uid(request), post_id=post_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PostCommentsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Comments on a post, oldest first, with their replies",
        parameters=[CommentQuerySerializer],
        responses={200: CommentListSerializer, **ERRORS},
        tags=["feed"],
    )
    def get(self, request: Request, post_id: UUID) -> Response:
        params = CommentQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        page = selectors.comments(request.user, post_id, **params.validated_data)
        response = Response(CommentListSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        summary="Comment on a post, or reply to a comment",
        description="Replies go one level deep: `parent_id` must be a top-level comment on this "
        "post. Limited per member per day.",
        request=CommentCreateSerializer,
        responses={
            201: CommentSerializer,
            **ERRORS,
            429: OpenApiResponse(description="Daily limit"),
        },
        tags=["feed"],
    )
    def post(self, request: Request, post_id: UUID) -> Response:
        _require(request, "feed.post")
        serializer = CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        comment = services.add_comment(
            user_id=_uid(request),
            post_id=post_id,
            body=data["body"],
            parent_id=data["parent_id"],
            mentions=data["mentions"],
        )
        view = selectors.get_comment(request.user, comment.pk)
        return Response(CommentSerializer(view).data, status=201)


class CommentView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Edit your comment",
        request=CommentUpdateSerializer,
        responses={200: CommentSerializer, **ERRORS},
        tags=["feed"],
    )
    def patch(self, request: Request, comment_id: UUID) -> Response:
        serializer = CommentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_comment(
            user_id=_uid(request), comment_id=comment_id, body=serializer.validated_data["body"]
        )
        return Response(CommentSerializer(selectors.get_comment(request.user, comment_id)).data)

    @extend_schema(
        summary="Delete your comment (and the replies under it)",
        responses={204: None, **ERRORS},
        tags=["feed"],
    )
    def delete(self, request: Request, comment_id: UUID) -> Response:
        services.delete_comment(user_id=_uid(request), comment_id=comment_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _reaction_result(
    request: Request, target_type: str, target_id: UUID, created: bool
) -> Response:
    if target_type == "post":
        view: dict[str, Any] = selectors.get_post(request.user, target_id)[1]
    else:
        view = selectors.get_comment(request.user, target_id)
    return Response(
        ReactionResultSerializer(
            {
                "created": created,
                "reactions": view["reactions"],
                "reaction_count": view["reaction_count"],
            }
        ).data,
        status=201 if created else 200,
    )


class ReactionsView(APIView):
    """Add a reaction to a post or a comment (the URL decides which)."""

    policy = policies.active_member
    target_type = "post"

    @extend_schema(
        summary="React",
        description="Idempotent: reacting the same way twice leaves one reaction (200).",
        request=ReactionSerializer,
        responses={201: ReactionResultSerializer, 200: ReactionResultSerializer, **ERRORS},
        tags=["feed"],
    )
    def post(self, request: Request, target_id: UUID) -> Response:
        serializer = ReactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = services.react(
            user_id=_uid(request),
            target_type=self.target_type,
            target_id=target_id,
            kind=serializer.validated_data["kind"],
        )
        return _reaction_result(request, self.target_type, target_id, created)


class CommentReactionsView(ReactionsView):
    target_type = "comment"


class ReactionDeleteView(APIView):
    policy = policies.active_member
    target_type = "post"

    @extend_schema(
        summary="Take a reaction back",
        responses={200: ReactionResultSerializer, **ERRORS},
        tags=["feed"],
    )
    def delete(self, request: Request, target_id: UUID, kind: str) -> Response:
        services.unreact(
            user_id=_uid(request), target_type=self.target_type, target_id=target_id, kind=kind
        )
        return _reaction_result(request, self.target_type, target_id, False)


class CommentReactionDeleteView(ReactionDeleteView):
    target_type = "comment"


class FollowsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Follow a member or a startup",
        description="Idempotent: following again answers 200. You can only follow someone whose "
        "profile (or a startup whose basics) you can see. Up to 500 follows.",
        request=FollowSerializer,
        responses={201: FollowResultSerializer, 200: FollowResultSerializer, **ERRORS},
        tags=["feed"],
    )
    def post(self, request: Request) -> Response:
        serializer = FollowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        created = follows.follow(viewer=request.user, kind=data["type"], target_id=data["id"])
        body = {"type": data["type"], "id": data["id"], "following": True}
        return Response(FollowResultSerializer(body).data, status=201 if created else 200)


class UnfollowView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Stop following",
        description="Idempotent: unfollowing someone you do not follow still answers 204.",
        responses={204: None, **ERRORS},
        tags=["feed"],
    )
    def delete(self, request: Request, kind: str, target_id: UUID) -> Response:
        if kind not in ("member", "startup"):
            raise exceptions.NotFound()
        follows.unfollow(user_id=_uid(request), kind=kind, target_id=target_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyFollowingView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Who you follow",
        description="Newest follow first. People and startups you can no longer see are left out.",
        parameters=[FollowingQuerySerializer],
        responses={200: FollowingListSerializer, **ERRORS},
        tags=["feed"],
    )
    def get(self, request: Request) -> Response:
        params = FollowingQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        page = follows.following(
            request.user, kind=data["type"], cursor=data["cursor"], limit=data["limit"]
        )
        response = Response(FollowingListSerializer(page).data)
        response["Cache-Control"] = "private, no-store"
        return response


class ReportView(APIView):
    """Report a post or a comment to the moderators (the URL decides which)."""

    policy = policies.active_member
    target_type = "post"

    @extend_schema(
        summary="Report to the moderators",
        description="You can report only what you can see, and not your own content. Reporting "
        "the same thing again answers 200 with the existing report. Limited per member per day.",
        request=ReportCreateSerializer,
        responses={
            201: ReportReceivedSerializer,
            200: ReportReceivedSerializer,
            **ERRORS,
            429: OpenApiResponse(description="Daily limit"),
        },
        tags=["feed"],
    )
    def post(self, request: Request, target_id: UUID) -> Response:
        serializer = ReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report, created = moderation.report(
            viewer=request.user,
            target_type=self.target_type,
            target_id=target_id,
            reason=data["reason"],
            details=data["details"],
        )
        body = {"id": report.pk, "status": report.status, "created": created}
        return Response(ReportReceivedSerializer(body).data, status=201 if created else 200)


class CommentReportView(ReportView):
    target_type = "comment"
