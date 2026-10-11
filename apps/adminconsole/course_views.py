from uuid import UUID

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.adminconsole.views import _actor, _ip
from apps.core import etag, policies
from apps.core.pagination import AdminLimitOffsetPagination
from apps.learning import authoring, learn, selectors
from apps.learning.models import Course, Lesson, Module
from apps.learning.serializers import (
    AdminCourseSerializer,
    AdminEnrolmentSerializer,
    AdminLessonSerializer,
    AdminModuleSerializer,
    AdminQuerySerializer,
    AdminRatingSerializer,
    CourseCoverSerializer,
    CourseCreateSerializer,
    CourseStatsSerializer,
    CourseUpdateSerializer,
    EnrolmentResultSerializer,
    GrantSerializer,
    LessonCreateSerializer,
    LessonUpdateSerializer,
    ModuleWriteSerializer,
    OrderSerializer,
)

MANAGE = policies.admin_permission("courses.manage")
IF_MATCH = OpenApiParameter("If-Match", str, OpenApiParameter.HEADER, required=True)
ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not allowed, or MFA missing"),
    404: OpenApiResponse(description="Not found"),
}


def _course(course_id: UUID) -> Course:
    course = Course.objects.exclude(status=Course.Status.REMOVED).filter(pk=course_id).first()
    if course is None:
        raise exceptions.NotFound()
    return course


def _one(course: Course, status_code: int = 200) -> Response:
    fresh = Course.objects.get(pk=course.pk)
    return etag.add_etag(
        Response(AdminCourseSerializer(selectors.admin_course(fresh)).data, status=status_code),
        fresh,
    )


class AdminCoursesView(APIView):
    policy = MANAGE

    @extend_schema(
        operation_id="admin_courses_list",
        summary="All courses, any state",
        parameters=[AdminQuerySerializer],
        responses={200: AdminCourseSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request) -> Response:
        params = AdminQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        filters = {k: v for k, v in params.validated_data.items() if k not in ("limit", "offset")}
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(selectors.admin_queryset(**filters), request, view=self)
        data = AdminCourseSerializer(
            [selectors.admin_course(c) for c in page or []], many=True
        ).data
        return paginator.get_paginated_response(data)

    @extend_schema(
        summary="Create a course",
        description="Starts as a draft. A paid course needs `price_minor` (smallest unit, above "
        "zero) and a three-letter `currency`; only free courses can be opened to visitors.",
        request=CourseCreateSerializer,
        responses={201: AdminCourseSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request) -> Response:
        serializer = CourseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = authoring.create_course(
            actor=_actor(request), data=dict(serializer.validated_data), ip=_ip(request)
        )
        return _one(course, 201)


class AdminCourseView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="One course", responses={200: AdminCourseSerializer, **ERRORS}, tags=["admin"]
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        return _one(_course(course_id))

    @extend_schema(
        summary="Edit a course",
        parameters=[IF_MATCH],
        request=CourseUpdateSerializer,
        responses={
            200: AdminCourseSerializer,
            **ERRORS,
            412: OpenApiResponse(description="Changed since the ETag was issued"),
            428: OpenApiResponse(description="If-Match header missing"),
        },
        tags=["admin"],
    )
    def patch(self, request: Request, course_id: UUID) -> Response:
        serializer = CourseUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = authoring.update_course(
            actor=_actor(request),
            course_id=course_id,
            data=dict(serializer.validated_data),
            if_match=request.headers.get("If-Match"),
            ip=_ip(request),
        )
        return _one(course)

    @extend_schema(summary="Remove a course", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, course_id: UUID) -> Response:
        authoring.remove_course(actor=_actor(request), course_id=course_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseActionView(APIView):
    """Publish, unpublish or duplicate (the URL names the action)."""

    policy = MANAGE
    action = ""

    @extend_schema(
        summary="Publish, unpublish or duplicate a course",
        description="Publishing needs at least one lesson. Unpublishing hides the course from the "
        "catalogue; people already enrolled keep their access and progress. Duplicating makes a "
        "draft copy of the modules and lessons (not enrolments, ratings or the cover).",
        request=None,
        responses={
            200: AdminCourseSerializer,
            201: AdminCourseSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not in a state that allows this"),
        },
        tags=["admin"],
    )
    def post(self, request: Request, course_id: UUID) -> Response:
        actor, ip = _actor(request), _ip(request)
        if self.action == "duplicate":
            return _one(authoring.duplicate(actor=actor, course_id=course_id, ip=ip), 201)
        call = authoring.publish if self.action == "publish" else authoring.unpublish
        return _one(call(actor=actor, course_id=course_id, ip=ip))


def action_view(action: str) -> type[CourseActionView]:
    return type(f"{action.title()}CourseView", (CourseActionView,), {"action": action})


class CourseCoverView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Use a finished upload as the cover",
        description="Upload with `POST /uploads` (purpose `course_cover`) and wait for `ready`.",
        request=CourseCoverSerializer,
        responses={200: AdminCourseSerializer, **ERRORS},
        tags=["admin"],
    )
    def put(self, request: Request, course_id: UUID) -> Response:
        serializer = CourseCoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = authoring.set_cover(
            actor=_actor(request),
            course_id=course_id,
            upload_id=serializer.validated_data["upload_id"],
        )
        return _one(course)

    @extend_schema(
        summary="Remove the cover", responses={200: AdminCourseSerializer, **ERRORS}, tags=["admin"]
    )
    def delete(self, request: Request, course_id: UUID) -> Response:
        return _one(authoring.set_cover(actor=_actor(request), course_id=course_id, upload_id=None))


# --- modules and lessons ---


class CourseModulesView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Add a module to the end of the course",
        request=ModuleWriteSerializer,
        responses={201: AdminModuleSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, course_id: UUID) -> Response:
        serializer = ModuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = authoring.add_module(
            actor=_actor(request),
            course_id=course_id,
            title=serializer.validated_data["title"],
            ip=_ip(request),
        )
        return Response(_module_body(module), status=status.HTTP_201_CREATED)


def _module_body(module: Module) -> dict[str, object]:
    course = Course.objects.get(pk=module.course_id)
    for row in selectors.admin_course(course)["modules"]:
        if row["id"] == module.pk:
            return AdminModuleSerializer(row).data
    return {}


class ModulesOrderView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Reorder the modules",
        description="List every module id once, in the order you want.",
        request=OrderSerializer,
        responses={
            200: AdminCourseSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not every module listed once"),
        },
        tags=["admin"],
    )
    def put(self, request: Request, course_id: UUID) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = authoring.reorder_modules(
            actor=_actor(request), course_id=course_id, ids=serializer.validated_data["ids"]
        )
        return _one(course)


class ModuleView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Rename a module",
        request=ModuleWriteSerializer,
        responses={200: AdminModuleSerializer, **ERRORS},
        tags=["admin"],
    )
    def patch(self, request: Request, module_id: UUID) -> Response:
        serializer = ModuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = authoring.update_module(
            actor=_actor(request), module_id=module_id, title=serializer.validated_data["title"]
        )
        return Response(_module_body(module))

    @extend_schema(
        summary="Delete a module and its lessons", responses={204: None, **ERRORS}, tags=["admin"]
    )
    def delete(self, request: Request, module_id: UUID) -> Response:
        authoring.delete_module(actor=_actor(request), module_id=module_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


def _lesson_body(lesson: Lesson) -> dict[str, object]:
    return AdminLessonSerializer(
        {
            "id": lesson.pk,
            "type": lesson.type,
            "title": lesson.title,
            "position": lesson.position,
            "duration_seconds": lesson.duration_seconds,
            "video_url": lesson.video_url,
            "video_id": lesson.video_id,
            "body": lesson.body,
            "resource_url": lesson.resource_url,
            "resource_name": lesson.resource_name,
        }
    ).data


class ModuleLessonsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Add a lesson to the end of a module",
        description="A video lesson takes a YouTube link (validated: https, youtube.com, "
        "youtu.be, a real 11-character video id; the id and normalised address are stored). A "
        "reading lesson takes `body`. A resource lesson takes `resource_url` and `resource_name`.",
        request=LessonCreateSerializer,
        responses={201: AdminLessonSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, module_id: UUID) -> Response:
        serializer = LessonCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = authoring.add_lesson(
            actor=_actor(request),
            module_id=module_id,
            data=dict(serializer.validated_data),
            ip=_ip(request),
        )
        return Response(_lesson_body(lesson), status=status.HTTP_201_CREATED)


class LessonsOrderView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Reorder the lessons in a module",
        request=OrderSerializer,
        responses={
            200: AdminModuleSerializer,
            **ERRORS,
            409: OpenApiResponse(description="Not every lesson listed once"),
        },
        tags=["admin"],
    )
    def put(self, request: Request, module_id: UUID) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = authoring.reorder_lessons(
            actor=_actor(request), module_id=module_id, ids=serializer.validated_data["ids"]
        )
        return Response(_module_body(module))


class LessonAdminView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Edit a lesson",
        request=LessonUpdateSerializer,
        responses={200: AdminLessonSerializer, **ERRORS},
        tags=["admin"],
    )
    def patch(self, request: Request, lesson_id: UUID) -> Response:
        serializer = LessonUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = authoring.update_lesson(
            actor=_actor(request), lesson_id=lesson_id, data=dict(serializer.validated_data)
        )
        return Response(_lesson_body(lesson))

    @extend_schema(summary="Delete a lesson", responses={204: None, **ERRORS}, tags=["admin"])
    def delete(self, request: Request, lesson_id: UUID) -> Response:
        authoring.delete_lesson(actor=_actor(request), lesson_id=lesson_id, ip=_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- people and results ---


class CourseStatsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Enrolments, completion rate, rating and per-lesson completion",
        responses={200: CourseStatsSerializer, **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        return Response(CourseStatsSerializer(selectors.stats(_course(course_id))).data)


class CourseEnrolmentsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Who is enrolled, and how far they have got",
        responses={200: AdminEnrolmentSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        course = _course(course_id)
        paginator = AdminLimitOffsetPagination()
        page = paginator.paginate_queryset(selectors.enrolment_rows(course), request, view=self)
        data = AdminEnrolmentSerializer(
            selectors.enrolment_views(page or [], course), many=True
        ).data
        return paginator.get_paginated_response(data)


class CourseRatingsView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Ratings and written feedback",
        responses={200: AdminRatingSerializer(many=True), **ERRORS},
        tags=["admin"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        return Response(
            AdminRatingSerializer(selectors.rating_rows(_course(course_id)), many=True).data
        )


class CourseGrantView(APIView):
    policy = MANAGE

    @extend_schema(
        summary="Give a member access to a course",
        description="The way into a paid course until purchasing exists. The member is told.",
        request=GrantSerializer,
        responses={201: EnrolmentResultSerializer, 200: EnrolmentResultSerializer, **ERRORS},
        tags=["admin"],
    )
    def post(self, request: Request, course_id: UUID) -> Response:
        serializer = GrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enrolment, created = learn.grant(
            actor=_actor(request),
            course_id=course_id,
            user_id=serializer.validated_data["user_id"],
            ip=_ip(request),
        )
        body = {
            "course_id": course_id,
            "origin": enrolment.source,
            "started_at": enrolment.started_at,
            "created": created,
        }
        return Response(
            EnrolmentResultSerializer(body).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
