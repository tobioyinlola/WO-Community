from django.urls import path, re_path

from apps.adminconsole import featured_views, invitation_views, reference_views, views

KINDS = "sectors|stages|skills"

urlpatterns = [
    re_path(
        rf"^admin/reference/(?P<kind>{KINDS})$",
        reference_views.ReferenceListView.as_view(),
        name="admin-reference",
    ),
    re_path(
        rf"^admin/reference/(?P<kind>{KINDS})/order$",
        reference_views.ReferenceOrderView.as_view(),
        name="admin-reference-order",
    ),
    re_path(
        rf"^admin/reference/(?P<kind>{KINDS})/(?P<item_id>[0-9a-f-]{{36}})$",
        reference_views.ReferenceItemView.as_view(),
        name="admin-reference-item",
    ),
    path(
        "admin/startups/<uuid:startup_id>/feature",
        featured_views.FeatureStartupView.as_view(),
        name="admin-startup-feature",
    ),
    path(
        "admin/startups/<uuid:startup_id>/unfeature",
        featured_views.UnfeatureStartupView.as_view(),
        name="admin-startup-unfeature",
    ),
    path(
        "admin/invitations",
        invitation_views.InvitationListCreateView.as_view(),
        name="admin-invitations",
    ),
    path(
        "admin/invitations/bulk",
        invitation_views.InvitationBulkView.as_view(),
        name="admin-invitations-bulk",
    ),
    path(
        "admin/invitations/<uuid:invitation_id>",
        invitation_views.InvitationDetailView.as_view(),
        name="admin-invitation",
    ),
    path(
        "admin/invitations/<uuid:invitation_id>/resend",
        invitation_views.InvitationResendView.as_view(),
        name="admin-invitation-resend",
    ),
    path(
        "admin/invitations/<uuid:invitation_id>/revoke",
        invitation_views.InvitationRevokeView.as_view(),
        name="admin-invitation-revoke",
    ),
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
