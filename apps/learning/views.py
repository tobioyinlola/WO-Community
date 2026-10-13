from typing import Any, cast
from uuid import UUID

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.authentication import OptionalJWTAuthentication
from apps.analytics import services as analytics
from apps.core import policies
from apps.core.public import PublicView
from apps.learning import certificates, learn, selectors
from apps.learning.models import Course
from apps.learning.serializers import (
    CatalogueQuerySerializer,
    CategoriesSerializer,
    CertificateChoiceSerializer,
    CertificateDownloadSerializer,
    CertificateSerializer,
    CourseDetailSerializer,
    CoursePageSerializer,
    EnrolmentResultSerializer,
    LessonDetailSerializer,
    LessonFileSerializer,
    LessonProgressResultSerializer,
    PageQuerySerializer,
    ProfileCertificateSerializer,
    ProgressSerializer,
    PublicCoursePageSerializer,
    PublicCourseSerializer,
    RatingSerializer,
    VerifiedCertificateSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member, or not enrolled"),
    404: OpenApiResponse(description="Not found"),
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


class CoursesView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="courses_list",
        summary="The course catalogue",
        description="Published courses, newest first. Filter by text, category, level, access "
        "(free or paid) or `enrolled=true`. Paid courses show their price and stay locked.",
        parameters=[CatalogueQuerySerializer],
        responses={200: CoursePageSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.catalogue(_uid(request), **_params(request, CatalogueQuerySerializer))
        return _private(Response(CoursePageSerializer(page).data))


class CategoriesView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Course categories in use",
        responses={200: CategoriesSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request) -> Response:
        return Response({"categories": selectors.categories()})


class CourseView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One course with its modules and lessons",
        description="Shows what is locked and what you have finished, and where to `resume`.",
        responses={200: CourseDetailSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, course_id: UUID) -> Response:
        return _private(
            Response(CourseDetailSerializer(selectors.course_detail(_uid(request), course_id)).data)
        )


class EnrolView(APIView):
    policy = policies.has_permission("learning.enrol")

    @extend_schema(
        summary="Enrol in a free course",
        description="One action, idempotent (200 if already enrolled). Paid courses answer 402 "
        "until purchasing exists; an admin can give access in the meantime.",
        request=None,
        responses={
            201: EnrolmentResultSerializer,
            200: EnrolmentResultSerializer,
            **ERRORS,
            402: OpenApiResponse(description="A paid course"),
        },
        tags=["learning"],
    )
    def post(self, request: Request, course_id: UUID) -> Response:
        enrolment, created = learn.enrol(user_id=_uid(request), course_id=course_id)
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


class MyCoursesView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Courses you are enrolled in, with progress",
        parameters=[PageQuerySerializer],
        responses={200: CoursePageSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.my_courses(_uid(request), **_params(request, PageQuerySerializer))
        return _private(Response(CoursePageSerializer(page).data))


class AnonymousLessonThrottle(SimpleRateThrottle):
    """Visitors opening free lessons get a tighter limit than members."""

    scope = "lesson_visitor"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        if request.user and request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LessonView(APIView):
    policy = policies.public  # members and, for courses open to visitors, anyone
    authentication_classes = [OptionalJWTAuthentication]
    throttle_classes = [UserRateThrottle, AnonymousLessonThrottle]

    @extend_schema(
        summary="Open a lesson",
        description="Video lessons give the YouTube video id and a privacy-enhanced embed "
        "address; reading lessons give their text; resource lessons their download link. "
        "Allowed for enrolled members, and for anyone on a free course the admin opened to "
        "visitors (with a stricter rate limit). Paid lessons need access; the video id is not "
        "sent to anyone without it.",
        responses={200: LessonDetailSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, lesson_id: UUID) -> Response:
        user = request.user if request.user and request.user.is_authenticated else None
        viewer_id = cast(UUID, user.pk) if user is not None and user.status == "active" else None
        return _private(
            Response(LessonDetailSerializer(selectors.lesson_detail(viewer_id, lesson_id)).data)
        )


class LessonFileView(APIView):
    policy = policies.public
    authentication_classes = [OptionalJWTAuthentication]
    throttle_classes = [UserRateThrottle, AnonymousLessonThrottle]

    @extend_schema(
        summary="Download link for a lesson document",
        description="For a resource lesson whose file we store. Returns a signed address that "
        "lasts a few minutes and saves the file as an attachment; ask again when it lapses. "
        "Same access rules as opening the lesson.",
        responses={200: LessonFileSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, lesson_id: UUID) -> Response:
        user = request.user if request.user and request.user.is_authenticated else None
        viewer_id = cast(UUID, user.pk) if user is not None and user.status == "active" else None
        return _private(
            Response(LessonFileSerializer(selectors.lesson_file(viewer_id, lesson_id)).data)
        )


class LessonProgressView(APIView):
    policy = policies.active_member
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "lesson_progress"

    @extend_schema(
        summary="Save progress in a lesson",
        description="The player calls this about every 15 seconds and on pause, and with "
        "`completed: true` when the member finishes. Finishing the last lesson completes the "
        "course and queues the certificate.",
        request=ProgressSerializer,
        responses={200: LessonProgressResultSerializer, **ERRORS},
        tags=["learning"],
    )
    def put(self, request: Request, lesson_id: UUID) -> Response:
        serializer = ProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        progress = learn.update_progress(
            user_id=_uid(request),
            lesson_id=lesson_id,
            position_seconds=data.get("position_seconds"),
            completed=data.get("completed"),
        )
        course = Course.objects.get(lessons=lesson_id)
        summary = learn.progress_summary(_uid(request), course)
        body = {
            "lesson_id": lesson_id,
            "position_seconds": progress.position_seconds,
            "completed": progress.completed_at is not None,
            "course_percent": summary["percent"],
            "course_completed": summary.get("completed_at") is not None,
        }
        return Response(LessonProgressResultSerializer(body).data)


class RatingView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Rate a course",
        description="Enrolled members only. Sending again changes your rating. Feedback is "
        "visible to admins.",
        request=RatingSerializer,
        responses={200: RatingSerializer, **ERRORS},
        tags=["learning"],
    )
    def put(self, request: Request, course_id: UUID) -> Response:
        serializer = RatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rating = learn.rate(user_id=_uid(request), course_id=course_id, **serializer.validated_data)
        return Response(RatingSerializer({"stars": rating.stars, "feedback": rating.feedback}).data)


class CertificatesView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Your certificates",
        responses={200: CertificateSerializer(many=True), **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request) -> Response:
        return _private(
            Response(
                CertificateSerializer(selectors.my_certificates(_uid(request)), many=True).data
            )
        )


class CertificateView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One of your certificates",
        responses={200: CertificateSerializer, **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, certificate_id: UUID) -> Response:
        certificate = selectors.get_certificate(_uid(request), certificate_id)
        return _private(
            Response(CertificateSerializer(selectors.certificate_view(certificate)).data)
        )

    @extend_schema(
        summary="Choose whether a certificate is listed on your profile",
        description="Off until you turn it on. A listed certificate shows the course, the date and "
        "a link to the verification page to members who may see your profile.",
        request=CertificateChoiceSerializer,
        responses={200: CertificateSerializer, **ERRORS},
        tags=["learning"],
    )
    def patch(self, request: Request, certificate_id: UUID) -> Response:
        data = CertificateChoiceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        certificate = selectors.set_show_on_profile(
            _uid(request), certificate_id, data.validated_data["show_on_profile"]
        )
        return _private(
            Response(CertificateSerializer(selectors.certificate_view(certificate)).data)
        )


class MemberCertificatesView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Certificates a member lists on their profile",
        description="Only certificates the member chose to show, and only if you may see their "
        "profile. A withdrawn certificate is never listed.",
        responses={200: ProfileCertificateSerializer(many=True), **ERRORS},
        tags=["learning"],
    )
    def get(self, request: Request, user_id: UUID) -> Response:
        return _private(
            Response(
                ProfileCertificateSerializer(
                    selectors.profile_certificates(request.user, user_id), many=True
                ).data
            )
        )


class CertificateDownloadView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="A short lived link to download your certificate as a PDF",
        description="The file is kept privately and the link stops working after a few minutes, "
        "so ask again when you need it. A revoked certificate cannot be downloaded.",
        responses={
            200: CertificateDownloadSerializer,
            409: OpenApiResponse(description="Revoked"),
            **ERRORS,
        },
        tags=["learning"],
    )
    def get(self, request: Request, certificate_id: UUID) -> Response:
        certificate = selectors.get_certificate(_uid(request), certificate_id)
        url, ttl, filename = certificates.download_link(certificate)
        analytics.track(
            "certificate_downloaded",
            actor_id=_uid(request),
            properties={"course_id": certificate.enrolment.course.slug},
        )
        return _private(
            Response(
                CertificateDownloadSerializer(
                    {"url": url, "expires_in": ttl, "filename": filename}
                ).data
            )
        )


# --- public ---


class PublicCoursesView(PublicView):
    @extend_schema(
        operation_id="public_courses_list",
        summary="Free courses open to visitors",
        parameters=[PageQuerySerializer],
        responses={200: PublicCoursePageSerializer, 400: OpenApiResponse(description="Bad query")},
        tags=["public"],
    )
    def get(self, request: Request) -> Response:
        page = selectors.public_courses(**_params(request, PageQuerySerializer))
        return self.cached(request, PublicCoursePageSerializer(page).data)


class PublicCourseView(PublicView):
    @extend_schema(
        summary="One free course open to visitors, with its outline",
        description="Lessons are opened with `GET /lessons/{id}`, which allows visitors for these "
        "courses.",
        responses={200: PublicCourseSerializer, 404: OpenApiResponse(description="Not found")},
        tags=["public"],
    )
    def get(self, request: Request, slug: str) -> Response:
        return self.cached(request, PublicCourseSerializer(selectors.public_course(slug)).data)


class VerifyCertificateView(PublicView):
    @extend_schema(
        summary="Check a certificate code",
        description="For employers and others holding a certificate: confirms who completed which "
        "course and when.",
        responses={
            200: VerifiedCertificateSerializer,
            404: OpenApiResponse(description="Unknown code"),
        },
        tags=["public"],
    )
    def get(self, request: Request, code: str) -> Response:
        return self.cached(request, VerifiedCertificateSerializer(selectors.verify(code)).data)
