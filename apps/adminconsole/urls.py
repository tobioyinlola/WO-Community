from django.urls import path

from apps.adminconsole import views

urlpatterns = [
    path("admin/queues", views.QueuesView.as_view(), name="admin-queues"),
    path("admin/members", views.MemberListView.as_view(), name="admin-members"),
    path("admin/members/<uuid:user_id>", views.MemberDetailView.as_view(), name="admin-member"),
    path(
        "admin/members/<uuid:user_id>/approve",
        views.ApproveView.as_view(),
        name="admin-member-approve",
    ),
    path(
        "admin/members/<uuid:user_id>/reject",
        views.RejectView.as_view(),
        name="admin-member-reject",
    ),
    path(
        "admin/members/<uuid:user_id>/suspend",
        views.SuspendView.as_view(),
        name="admin-member-suspend",
    ),
    path(
        "admin/members/<uuid:user_id>/reinstate",
        views.ReinstateView.as_view(),
        name="admin-member-reinstate",
    ),
    path(
        "admin/members/<uuid:user_id>/reset-mfa",
        views.ResetMfaView.as_view(),
        name="admin-member-reset-mfa",
    ),
    path(
        "admin/members/<uuid:user_id>/remove",
        views.RemoveView.as_view(),
        name="admin-member-remove",
    ),
]
