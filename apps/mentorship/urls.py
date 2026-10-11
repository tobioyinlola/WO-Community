from django.urls import path

from apps.mentorship import views

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
]
