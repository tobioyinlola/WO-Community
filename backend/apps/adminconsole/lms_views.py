from typing import Any, cast
from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.adminconsole.views import _ip
from apps.core import policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.integrations import youtube
from apps.learning import authoring, engage, lms_admin
from apps.learning.lms_serializers import (
    AdminAccessRequestSerializer,
    AdminLearnerSerializer,
    AdminQuestionSerializer,
    AdminRequestsQuerySerializer,
    AdminReviewSerializer,
    AnnouncementCreateSerializer,
    AnnouncementSerializer,
    BodySerializer,
    BulkLinksSerializer,
    YouTubeCheckedSerializer,
    YouTubeValidateSerializer,
)
from apps.learning.models import Course, CourseAnnouncement, LectureQuestion
from apps.learning.serializers import AdminLessonSerializer

MANAGE = policies.admin_permission("courses.manage")
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _actor(request: Request) -> User:
    return cast(User, request.user)


def _course(course_id: UUID) -> Course:
    course = Course.objects.filter(pk=course_id).exclude(status=Course.Status.REMOVED).first()
    if course is None:
        raise exceptions.NotFound()
    return course


class AccessRequestsView(APIView):
    """Every open request across courses, for the nav item; or one course's, for its tab."""

    policy = MANAGE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    def _page(self, request: Request, course: Course | None) -> Response:
        params = AdminRequestsQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            lms_admin.request_rows(course, params.validated_data["status"]), request, view=self
        )
        return paginator.get_paginated_response(
            AdminAccessRequestSerializer(lms_admin.request_views(list(page or [])), many=True).data
        )

    @extend_schema(
        operation_id="admin_course_requests_all",
        summary="Requests for access to paid courses, across all courses",
        parameters=[AdminRequestsQuerySerializer],
        responses={200: AdminAccessRequestSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        return self._page(request, None)


class CourseRequestsView(AccessRequestsView):
    @extend_schema(
        operation_id="admin_course_requests",
        summary="Requests for access to one course",
        parameters=[AdminRequestsQuerySerializer],
        responses={200: AdminAccessRequestSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:  # type: ignore[override]
        return self._page(request, _course(course_id))


class RequestDecisionView(APIView):
    policy = MANAGE
    approve = True

    @extend_schema(
        summary="Approve or decline a request for access",
        description="Approving gives the member the course and tells them. Declining tells them "
        "too. A request is decided once.",
        request=None,
        responses={
            200: AdminAccessRequestSerializer,
            409: OpenApiResponse(description="Already decided"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request, request_id: UUID) -> Response:
        decided = engage.decide_request(
            actor=_actor(request), request_id=request_id, approve=self.approve, ip=_ip(request)
        )
        [view] = lms_admin.request_views([decided])
        return Response(AdminAccessRequestSerializer(view).data)


class ApproveRequestView(RequestDecisionView):
    approve = True


class DeclineRequestView(RequestDecisionView):
    approve = False


class CourseLearnersView(APIView):
    policy = MANAGE
    pagination_class = AdminLimitOffsetPagination  # documents the page shape

    @extend_schema(
        summary="Learners, with their name, email and how far they have got",
        responses={200: AdminLearnerSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        course = _course(course_id)
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(
            course.enrolments.order_by("-started_at", "-id"), request, view=self
        )
        data = AdminLearnerSerializer(
            lms_admin.learner_views(course, list(page or [])), many=True
        ).data
        return paginator.get_paginated_response(data)


class LearnerView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Take a learner off a course",
        description="Their progress goes with the enrolment. Their certificate, if issued, stays.",
        responses={204: OpenApiResponse(description="Removed"), **ERRORS},
        tags=["admin"],
    )
    def delete(self, request: Request, course_id: UUID, user_id: UUID) -> Response:
        engage.remove_enrolment(
            actor=_actor(request), course_id=course_id, user_id=user_id, ip=_ip(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseLearnersCsvView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="The learners as a spreadsheet",
        responses={(200, "text/csv"): OpenApiResponse(description="CSV"), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> HttpResponse:
        course = _course(course_id)
        response = HttpResponse(
            lms_admin.learners_csv(course), content_type="text/csv; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="learners-{course.slug}.csv"'
        response["Cache-Control"] = "private, no-store"
        return response


class CourseReviewsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Every review, including hidden ones",
        responses={200: AdminReviewSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        return Response(
            AdminReviewSerializer(lms_admin.review_views(_course(course_id)), many=True).data
        )


class ModerationView(APIView):
    """Hide or restore a review, question or answer."""

    policy = MANAGE
    kind = "review"
    hidden = True

    @extend_schema(
        summary="Hide or restore a review, question or answer",
        description="A hidden review leaves the average and the distribution.",
        request=None,
        responses={204: OpenApiResponse(description="Done"), **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, item_id: UUID) -> Response:
        engage.set_hidden(
            actor=_actor(request),
            kind=self.kind,
            item_id=item_id,
            hidden=self.hidden,
            ip=_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def moderation(kind: str, hidden: bool) -> type[ModerationView]:
    name = f"{'Hide' if hidden else 'Restore'}{kind.title()}View"
    return type(name, (ModerationView,), {"kind": kind, "hidden": hidden})


class CourseQuestionsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Questions on a course's lectures, with answers",
        responses={200: AdminQuestionSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        return Response(
            AdminQuestionSerializer(lms_admin.question_views(_course(course_id)), many=True).data
        )


class StaffAnswerView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Answer a question as course staff",
        description="The answer carries the staff badge and the asker is told.",
        request=BodySerializer,
        responses={201: AdminQuestionSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, question_id: UUID) -> Response:
        data = BodySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        question = LectureQuestion.objects.filter(pk=question_id).first()
        if question is None:
            raise exceptions.NotFound()
        engage.answer(
            user=_actor(request), question_id=question_id, body=data.validated_data["body"]
        )
        [view] = [q for q in lms_admin.question_views(question.course) if q["id"] == question_id]
        return Response(AdminQuestionSerializer(view).data, status=status.HTTP_201_CREATED)


class CourseAnnouncementsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Announcements posted to a course",
        responses={200: AnnouncementSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        rows = CourseAnnouncement.objects.filter(course=_course(course_id)).order_by("-created_at")[
            :50
        ]
        body = [
            {"id": a.pk, "title": a.title, "body": a.body, "created_at": a.created_at} for a in rows
        ]
        return Response(AnnouncementSerializer(body, many=True).data)

    @extend_schema(
        summary="Post an announcement",
        description="Every enrolled learner is told, in the app and by email.",
        request=AnnouncementCreateSerializer,
        responses={201: AnnouncementSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, course_id: UUID) -> Response:
        data = AnnouncementCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item = engage.announce(
            actor=_actor(request), course_id=course_id, ip=_ip(request), **data.validated_data
        )
        body = {
            "id": item.pk,
            "title": item.title,
            "body": item.body,
            "created_at": item.created_at,
        }
        return Response(AnnouncementSerializer(body).data, status=status.HTTP_201_CREATED)


class YouTubeValidateView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Check a YouTube link and get its title and thumbnail",
        description="Only YouTube video links are accepted. The title may be blank when YouTube "
        "could not be asked.",
        request=YouTubeValidateSerializer,
        responses={
            200: YouTubeCheckedSerializer,
            400: OpenApiResponse(description="Not a YouTube video link"),
            **ERRORS,
        },
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        data = YouTubeValidateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            video = youtube.parse(data.validated_data["url"])
        except youtube.InvalidVideoUrl as exc:
            raise exceptions.ValidationError({"url": [str(exc)]}) from exc
        body = {
            "video_id": video.video_id,
            "url": video.url,
            "title": youtube.title_of(video.video_id),
            "thumbnail": youtube.thumbnail_url(video.video_id),
        }
        return Response(YouTubeCheckedSerializer(body).data)


class BulkLecturesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Add a lecture for each pasted YouTube link",
        description="All or nothing: a wrong link adds none and is named. Titles come from YouTube "
        "when it can be asked.",
        request=BulkLinksSerializer,
        responses={201: AdminLessonSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, module_id: UUID) -> Response:
        data = BulkLinksSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        lessons = authoring.add_lessons_from_links(
            actor=_actor(request),
            module_id=module_id,
            urls=data.validated_data["urls"],
            ip=_ip(request),
        )
        from apps.adminconsole.course_views import _lesson_body

        body: list[Any] = [_lesson_body(lesson) for lesson in lessons]
        return Response(body, status=status.HTTP_201_CREATED)
