from django.urls import path

from apps.startups import views

urlpatterns = [
    path("startups", views.StartupCreateView.as_view(), name="startup-create"),
    path("me/startups", views.MyStartupsView.as_view(), name="my-startups"),
    path("startups/<uuid:startup_id>", views.StartupDetailView.as_view(), name="startup-detail"),
    path(
        "startups/<uuid:startup_id>/visibility",
        views.StartupVisibilityView.as_view(),
        name="startup-visibility",
    ),
    path(
        "startups/<uuid:startup_id>/traction",
        views.StartupTractionView.as_view(),
        name="startup-traction",
    ),
    path("startups/<uuid:startup_id>/team", views.StartupTeamView.as_view(), name="startup-team"),
    path(
        "startups/<uuid:startup_id>/team/<uuid:member_id>",
        views.StartupTeamMemberView.as_view(),
        name="startup-team-member",
    ),
]
