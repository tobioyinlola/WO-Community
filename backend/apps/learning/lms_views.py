from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core import policies
from apps.learning import engage, lms_selectors
from apps.learning.lms_serializers import (
    AccessRequestResultSerializer,
    AccessRequestSerializer,
    AnnouncementSerializer,
    AnswerSerializer,
    BodySerializer,
    CoursePageDetailSerializer,
    NoteCreateSerializer,
    NoteSerializer,
    QuestionSerializer,
    ReviewPageSerializer,
    ReviewsQuerySerializer,
    WishlistStateSerializer,
)
from apps.learning.serializers import CoursePageSerializer, ShelfQuerySerializer

ERRORS = {
    401: OpenApiResponse(description="Not logged in"),
    403: OpenApiResponse(description="Not an active member, or not enrolled"),
    404: OpenApiResponse(description="Not found"),
}


def _user(request: Request) -> User:
    return cast(User, request.user)


def _query(request: Request, serializer_class: Any) -> dict[str, Any]:
    params = serializer_class(data=request.query_params.dict())
    params.is_valid(raise_exception=True)
    return dict(params.validated_data)


def _private(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class CoursePageView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="course_page",
        summary="A course landing page, by its id or its slug",
        description="The outline and description, what you will learn, requirements, the promo "
        "video, rating distribution, related courses, and where you are in it. Lectures marked "
        "as previews are not locked.",
        responses={200: CoursePageDetailSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, ref: str) -> Response:
        page = lms_selectors.course_page(_user(request).pk, ref)
        return _private(Response(CoursePageDetailSerializer(page).data))


class ReviewsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Reviews of a course, newest first",
        parameters=[ReviewsQuerySerializer],
        responses={200: ReviewPageSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        page = lms_selectors.reviews(
            _user(request).pk, course_id, **_query(request, ReviewsQuerySerializer)
        )
        return _private(Response(ReviewPageSerializer(page).data))


class WishlistView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Save a course for later",
        request=None,
        responses={200: WishlistStateSerializer, **ERRORS},
        tags=["learning"],
    )
    def put(self, request: Request, course_id: UUID) -> Response:
        engage.set_wishlist(user_id=_user(request).pk, course_id=course_id, saved=True)
        return Response({"saved": True})

    @extend_schema(
        summary="Take a course off your saved list",
        responses={200: WishlistStateSerializer, **ERRORS},
        tags=["learning"],
    )
    def delete(self, request: Request, course_id: UUID) -> Response:
        engage.set_wishlist(user_id=_user(request).pk, course_id=course_id, saved=False)
        return Response({"saved": False})


class ShelfView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your learning: all, in progress, completed, or saved",
        parameters=[ShelfQuerySerializer],
        responses={200: CoursePageSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request) -> Response:
        page = lms_selectors.shelf(_user(request).pk, **_query(request, ShelfQuerySerializer))
        return _private(Response(CoursePageSerializer(page).data))


class AccessRequestView(APIView):
    policy = policies.has_permission("learning.enrol")
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "course_request"

    @extend_schema(
        summary="Ask for access to a paid course",
        description="While payments are off, an admin decides. One open request at a time.",
        request=AccessRequestSerializer,
        responses={
            201: AccessRequestResultSerializer,
            409: OpenApiResponse(description="Free course, already enrolled, or enrolment closed"),
            **ERRORS,
        },
        tags=["learning"],
    )
    def post(self, request: Request, course_id: UUID) -> Response:
        data = AccessRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        asked = engage.request_access(
            user_id=_user(request).pk, course_id=course_id, message=data.validated_data["message"]
        )
        return Response(
            AccessRequestResultSerializer(
                {"id": asked.pk, "status": asked.status, "created_at": asked.created_at}
            ).data,
            status=status.HTTP_201_CREATED,
        )


class QuestionsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Questions on a lecture, with their answers",
        responses={200: QuestionSerializer(many=True), **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, lesson_id: UUID) -> Response:
        return _private(
            Response(
                QuestionSerializer(
                    lms_selectors.questions(_user(request), lesson_id), many=True
                ).data
            )
        )

    @extend_schema(
        summary="Ask a question about a lecture",
        request=BodySerializer,
        responses={201: QuestionSerializer, **ERRORS},
        tags=["learning"],
    )
    def post(self, request: Request, lesson_id: UUID) -> Response:
        data = BodySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        asked = engage.ask(
            user=_user(request), lesson_id=lesson_id, body=data.validated_data["body"]
        )
        shown = next(
            q for q in lms_selectors.questions(_user(request), lesson_id) if q["id"] == asked.pk
        )
        return Response(QuestionSerializer(shown).data, status=status.HTTP_201_CREATED)


class AnswersView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Answer a question",
        request=BodySerializer,
        responses={201: AnswerSerializer, **ERRORS},
        tags=["learning"],
    )
    def post(self, request: Request, question_id: UUID) -> Response:
        data = BodySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        reply = engage.answer(
            user=_user(request), question_id=question_id, body=data.validated_data["body"]
        )
        body = {
            "id": reply.pk,
            "body": reply.body,
            "author": "You",
            "is_staff": reply.is_staff,
            "mine": True,
            "created_at": reply.created_at,
        }
        return Response(AnswerSerializer(body).data, status=status.HTTP_201_CREATED)


class NotesView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your private notes on a lecture",
        responses={200: NoteSerializer(many=True), **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, lesson_id: UUID) -> Response:
        return _private(
            Response(
                NoteSerializer(lms_selectors.notes(_user(request).pk, lesson_id), many=True).data
            )
        )

    @extend_schema(
        summary="Keep a note at a moment in a lecture",
        request=NoteCreateSerializer,
        responses={201: NoteSerializer, **ERRORS},
        tags=["learning"],
    )
    def post(self, request: Request, lesson_id: UUID) -> Response:
        data = NoteCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        note = engage.add_note(
            user_id=_user(request).pk, lesson_id=lesson_id, **data.validated_data
        )
        body = {
            "id": note.pk,
            "seconds": note.seconds,
            "body": note.body,
            "created_at": note.created_at,
        }
        return Response(NoteSerializer(body).data, status=status.HTTP_201_CREATED)


class NoteView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Delete one of your notes",
        responses={204: OpenApiResponse(description="Deleted"), **ERRORS},
        tags=["learning"],
    )
    def delete(self, request: Request, note_id: UUID) -> Response:
        engage.delete_note(user_id=_user(request).pk, note_id=note_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AnnouncementsView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Announcements posted to a course",
        responses={200: AnnouncementSerializer(many=True), **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        rows = lms_selectors.announcements(_user(request), course_id)
        return _private(Response(AnnouncementSerializer(rows, many=True).data))
