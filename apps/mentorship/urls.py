from django.urls import path

from apps.mentorship import session_views, views

urlpatterns = [
    path("mentor-applications", views.MentorApplicationsView.as_view(), name="mentor-applications"),
    path(
        "mentor-applications/<uuid:application_id>",
        views.MentorApplicationView.as_view(),
        name="mentor-application",
    ),
    path(
        "me/mentor-application",
        views.MyMentorApplicationView.as_view(),
        name="my-mentor-application",
    ),
    path("me/mentoring", views.MyMentoringView.as_view(), name="my-mentoring"),
    path("me/mentor-profile", views.MyMentorProfileView.as_view(), name="my-mentor-profile"),
    path("me/availability", views.MyAvailabilityView.as_view(), name="my-availability"),
    path("me/mentorship-needs", views.MyNeedsView.as_view(), name="my-mentorship-needs"),
    path("mentors", views.MentorsView.as_view(), name="mentors"),
    path("mentors/recommended", views.RecommendedMentorsView.as_view(), name="mentors-recommended"),
    path("mentors/<uuid:user_id>", views.MentorView.as_view(), name="mentor"),
    path(
        "mentors/<uuid:user_id>/availability",
        views.MentorAvailabilityView.as_view(),
        name="mentor-availability",
    ),
    path(
        "sessions",
        session_views.SessionsView.as_view(),
        name="sessions",
    ),
    path(
        "sessions/<uuid:session_id>",
        session_views.SessionView.as_view(),
        name="session",
    ),
    path(
        "sessions/<uuid:session_id>/accept",
        session_views.SessionAcceptView.as_view(),
        name="session-accept",
    ),
    path(
        "sessions/<uuid:session_id>/decline",
        session_views.SessionDeclineView.as_view(),
        name="session-decline",
    ),
    path(
        "sessions/<uuid:session_id>/cancel",
        session_views.SessionCancelView.as_view(),
        name="session-cancel",
    ),
    path(
        "sessions/<uuid:session_id>/reschedule",
        session_views.SessionRescheduleView.as_view(),
        name="session-reschedule",
    ),
    path(
        "sessions/<uuid:session_id>/reschedule/accept",
        session_views.SessionRescheduleAcceptView.as_view(),
        name="session-reschedule-accept",
    ),
    path(
        "sessions/<uuid:session_id>/meeting-link",
        session_views.SessionMeetingLinkView.as_view(),
        name="session-meeting-link",
    ),
    path(
        "sessions/<uuid:session_id>/feedback",
        session_views.SessionFeedbackView.as_view(),
        name="session-feedback",
    ),
    path(
        "sessions/<uuid:session_id>/calendar.ics",
        session_views.SessionCalendarView.as_view(),
        name="session-calendar",
    ),
]
