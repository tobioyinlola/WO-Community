from django.urls import path

from apps.toolkit.ventures import views

urlpatterns = [
    path("ventures", views.VenturesView.as_view(), name="tk-ventures"),
    path("ventures/<uuid:venture_id>", views.VentureView.as_view(), name="tk-venture"),
    path(
        "ventures/<uuid:venture_id>/restore",
        views.VentureRestoreView.as_view(),
        name="tk-venture-restore",
    ),
    path(
        "ventures/<uuid:venture_id>/export",
        views.VentureExportView.as_view(),
        name="tk-venture-export",
    ),
    path(
        "ventures/<uuid:venture_id>/package", views.PackageView.as_view(), name="tk-venture-package"
    ),
    path("ventures/<uuid:venture_id>/profile", views.ProfileView.as_view(), name="tk-profile"),
    path(
        "ventures/<uuid:venture_id>/profile/import-startup",
        views.ImportStartupView.as_view(),
        name="tk-profile-import",
    ),
    path(
        "ventures/<uuid:venture_id>/profile/versions",
        views.ProfileVersionsView.as_view(),
        name="tk-profile-versions",
    ),
    path(
        "ventures/<uuid:venture_id>/competitors",
        views.CompetitorsView.as_view(),
        name="tk-competitors",
    ),
    path(
        "ventures/<uuid:venture_id>/competitors/<uuid:competitor_id>",
        views.CompetitorView.as_view(),
        name="tk-competitor",
    ),
    path("ventures/<uuid:venture_id>/team", views.TeamView.as_view(), name="tk-team"),
    path(
        "ventures/<uuid:venture_id>/team/<uuid:member_id>",
        views.TeamMemberView.as_view(),
        name="tk-team-member",
    ),
]
