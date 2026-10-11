from typing import cast
from uuid import UUID

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import policies
from apps.mentorship import booking, feedback, session_selectors
from apps.mentorship.session_serializers import (
    FeedbackItemSerializer,
    MeetingLinkSerializer,
    MentoringSessionPageSerializer,
    MentoringSessionSerializer,
    RescheduleSerializer,
    SessionFeedbackSerializer,
    SessionOptionalReasonSerializer,
    SessionQuerySerializer,
    SessionReasonSerializer,
    SessionRequestSerializer,
)

ERRORS = {
    401: OpenApiResponse(description="Not authenticated"),
    403: OpenApiResponse(description="Not an active member, or not allowed to do this"),
    404: OpenApiResponse(description="Not found, or not your session"),
    409: OpenApiResponse(description="The session is not in a state that allows this"),
}


def _uid(request: Request) -> UUID:
    return cast(UUID, request.user.pk)


def _one(request: Request, session_id: UUID, status_code: int = 200) -> Response:
    data = session_selectors.detail(_uid(request), session_id)
    response = Response(MentoringSessionSerializer(data).data, status=status_code)
    response["Cache-Control"] = "private, no-store"
    return response


class SessionsView(APIView):
    policy = policies.active_member

    @extend_schema(
        operation_id="sessions_list",
        summary="Your mentoring sessions",
        description="Sessions where you are the mentor or the founder. `state` picks the list; "
        "upcoming and pending are soonest first, the rest newest first.",
        parameters=[SessionQuerySerializer],
        responses={200: MentoringSessionPageSerializer, **ERRORS},
        tags=["sessions"],
    )
    def get(self, request: Request) -> Response:
        query = SessionQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        data = query.validated_data
        body = session_selectors.page(
            _uid(request),
            role=data.get("role", ""),
            state=data["state"],
            cursor=data["cursor"],
            limit=data["limit"],
        )
        response = Response(MentoringSessionPageSerializer(body).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        summary="Ask a mentor for a session",
        description="Pick one of the mentor's bookable times. The time is held for you while "
        "the mentor decides (they have 72 hours, and the request lapses a couple of hours before "
        "it starts). You can have 5 requests waiting and make 10 a day, and only one waiting "
        "request per mentor. Two people asking for the same time at once is settled by the "
        "database: the second gets 409.",
        request=SessionRequestSerializer,
        responses={
            201: MentoringSessionSerializer,
            **ERRORS,
            429: OpenApiResponse(description="Limit"),
        },
        tags=["sessions"],
    )
    def post(self, request: Request) -> Response:
        serializer = SessionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = booking.request(user_id=_uid(request), **serializer.validated_data)
        return _one(request, session.pk, 201)


class SessionView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="One session",
        description="Only the mentor and the founder can see it. The meeting address appears "
        "once the session is confirmed and the meeting is ready.",
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def get(self, request: Request, session_id: UUID) -> Response:
        return _one(request, session_id)


class SessionAcceptView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Confirm a request (mentor)",
        description="Confirms the session and starts creating the video meeting.",
        request=None,
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        booking.accept(user_id=_uid(request), session_id=session_id)
        return _one(request, session_id)


class SessionDeclineView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Decline a request (mentor)",
        description="The reason is shown to the founder.",
        request=SessionReasonSerializer,
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        serializer = SessionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking.decline(
            user_id=_uid(request),
            session_id=session_id,
            reason=serializer.validated_data["reason"],
        )
        return _one(request, session_id)


class SessionCancelView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Cancel a session, or withdraw a request",
        description="Either person can cancel before the start. A confirmed session needs a "
        "reason, which the other person sees; cancelling inside 24 hours is marked as late. A "
        "mentor answers a waiting request with decline instead.",
        request=SessionOptionalReasonSerializer,
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        serializer = SessionOptionalReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking.cancel(
            user_id=_uid(request),
            session_id=session_id,
            reason=serializer.validated_data["reason"],
        )
        return _one(request, session_id)


class SessionRescheduleView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Suggest a new time",
        description="Either person can suggest one of the mentor's bookable times for a "
        "confirmed session. The session keeps its time until the other person accepts. A "
        "session can be moved 3 times.",
        request=RescheduleSerializer,
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        serializer = RescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking.propose_reschedule(
            user_id=_uid(request), session_id=session_id, **serializer.validated_data
        )
        return _one(request, session_id)

    @extend_schema(
        summary="Withdraw your suggestion, or keep the original time",
        description="The person who suggested the time takes it back; the other person says no. "
        "Either way the session keeps its time.",
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def delete(self, request: Request, session_id: UUID) -> Response:
        booking.close_reschedule(user_id=_uid(request), session_id=session_id)
        return _one(request, session_id)


class SessionRescheduleAcceptView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Accept the suggested new time",
        description="Only the person who did not suggest it. The time is checked again, and "
        "409 means it was taken meanwhile.",
        request=None,
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def post(self, request: Request, session_id: UUID) -> Response:
        booking.accept_reschedule(user_id=_uid(request), session_id=session_id)
        return _one(request, session_id)


class SessionMeetingLinkView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Add your own meeting link (mentor)",
        description="Only when the platform could not create a video meeting "
        "(`meeting.state` is `failed`).",
        request=MeetingLinkSerializer,
        responses={200: MentoringSessionSerializer, **ERRORS},
        tags=["sessions"],
    )
    def put(self, request: Request, session_id: UUID) -> Response:
        serializer = MeetingLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking.set_meeting_link(
            user_id=_uid(request), session_id=session_id, url=serializer.validated_data["url"]
        )
        return _one(request, session_id)


class SessionFeedbackView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Give feedback on a finished session",
        description="Founders: 1 to 5 stars and an optional comment (shown to the mentor and "
        "admins, never publicly), or report that the mentor did not come. Mentors: whether the "
        "session was held or the founder missed it. Open for 14 days after the session; sending "
        "again replaces your earlier feedback.",
        request=SessionFeedbackSerializer,
        responses={200: FeedbackItemSerializer, **ERRORS},
        tags=["sessions"],
    )
    def put(self, request: Request, session_id: UUID) -> Response:
        serializer = SessionFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = feedback.submit(
            user_id=_uid(request), session_id=session_id, data=dict(serializer.validated_data)
        )
        body = {
            "stars": row.stars,
            "comment": row.comment,
            "outcome": row.outcome,
            "updated_at": row.updated_at,
        }
        response = Response(FeedbackItemSerializer(body).data)
        response["Cache-Control"] = "private, no-store"
        return response


class SessionCalendarView(APIView):
    policy = policies.active_member

    @extend_schema(
        summary="Add a session to your calendar",
        description="An iCalendar (.ics) file.",
        responses={(200, "text/calendar"): OpenApiResponse(description="iCalendar file"), **ERRORS},
        tags=["sessions"],
    )
    def get(self, request: Request, session_id: UUID) -> HttpResponse:
        body = session_selectors.calendar_file(_uid(request), session_id)
        response = HttpResponse(body, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="mentoring-session.ics"'
        response["Cache-Control"] = "private, no-store"
        return response
