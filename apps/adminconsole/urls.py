from django.urls import path, re_path

from apps.adminconsole import (
    campaign_views,
    course_views,
    dashboard_views,
    editorial_views,
    event_views,
    featured_views,
    feed_views,
    invitation_views,
    job_views,
    reference_views,
    views,
)

KINDS = "sectors|stages|skills"

COURSE_ACTIONS = ("publish", "unpublish", "duplicate")
CAMPAIGN_ACTIONS = ("send", "schedule", "unschedule", "pause", "resume", "cancel", "test")
EVENT_ACTIONS = ("publish", "unpublish", "cancel")
ITEM_ACTIONS = ("publish", "unpublish")
COMMENT_ACTIONS_ITEM = ("hide", "unhide", "remove")
WIN_DECISIONS = ("approve", "reject")
JOB_DECISIONS = ("approve", "reject", "unpublish", "remove")
POST_ACTIONS = ("pin", "unpin", "feature", "unfeature", "hide", "unhide", "remove")

COMMENT_ACTIONS = ("hide", "unhide", "remove")

urlpatterns = [
    path("admin/courses", course_views.AdminCoursesView.as_view(), name="admin-courses"),
    path(
        "admin/courses/<uuid:course_id>",
        course_views.AdminCourseView.as_view(),
        name="admin-course",
    ),
    path(
        "admin/courses/<uuid:course_id>/cover",
        course_views.CourseCoverView.as_view(),
        name="admin-course-cover",
    ),
    path(
        "admin/courses/<uuid:course_id>/modules",
        course_views.CourseModulesView.as_view(),
        name="admin-course-modules",
    ),
    path(
        "admin/courses/<uuid:course_id>/modules/order",
        course_views.ModulesOrderView.as_view(),
        name="admin-course-modules-order",
    ),
    path(
        "admin/courses/<uuid:course_id>/stats",
        course_views.CourseStatsView.as_view(),
        name="admin-course-stats",
    ),
    path(
        "admin/courses/<uuid:course_id>/enrolments",
        course_views.CourseEnrolmentsView.as_view(),
        name="admin-course-enrolments",
    ),
    path(
        "admin/courses/<uuid:course_id>/ratings",
        course_views.CourseRatingsView.as_view(),
        name="admin-course-ratings",
    ),
    path(
        "admin/courses/<uuid:course_id>/grant",
        course_views.CourseGrantView.as_view(),
        name="admin-course-grant",
    ),
    *[
        path(
            f"admin/courses/<uuid:course_id>/{action}",
            course_views.action_view(action).as_view(),
            name=f"admin-course-{action}",
        )
        for action in COURSE_ACTIONS
    ],
    path("admin/modules/<uuid:module_id>", course_views.ModuleView.as_view(), name="admin-module"),
    path(
        "admin/modules/<uuid:module_id>/lessons",
        course_views.ModuleLessonsView.as_view(),
        name="admin-module-lessons",
    ),
    path(
        "admin/modules/<uuid:module_id>/lessons/order",
        course_views.LessonsOrderView.as_view(),
        name="admin-module-lessons-order",
    ),
    path(
        "admin/lessons/<uuid:lesson_id>",
        course_views.LessonAdminView.as_view(),
        name="admin-lesson",
    ),
    path("admin/dashboard", dashboard_views.DashboardView.as_view(), name="admin-dashboard"),
    path(
        "admin/dashboard/metrics",
        dashboard_views.MetricsView.as_view(),
        name="admin-dashboard-metrics",
    ),
    path(
        "admin/dashboard/series",
        dashboard_views.SeriesView.as_view(),
        name="admin-dashboard-series",
    ),
    path(
        "admin/dashboard/funnel",
        dashboard_views.FunnelView.as_view(),
        name="admin-dashboard-funnel",
    ),
    path(
        "admin/dashboard/refresh",
        dashboard_views.RefreshView.as_view(),
        name="admin-dashboard-refresh",
    ),
    path("admin/segments", campaign_views.SegmentsView.as_view(), name="admin-segments"),
    path(
        "admin/segments/preview",
        campaign_views.SegmentPreviewView.as_view(),
        name="admin-segment-preview",
    ),
    path(
        "admin/segments/<uuid:segment_id>",
        campaign_views.SegmentView.as_view(),
        name="admin-segment",
    ),
    path(
        "admin/segments/<uuid:segment_id>/preview",
        campaign_views.SavedSegmentPreviewView.as_view(),
        name="admin-segment-saved-preview",
    ),
    path(
        "admin/campaign-templates",
        campaign_views.TemplatesView.as_view(),
        name="admin-campaign-templates",
    ),
    path(
        "admin/campaign-templates/<uuid:template_id>",
        campaign_views.TemplateView.as_view(),
        name="admin-campaign-template",
    ),
    path("admin/campaigns", campaign_views.CampaignsView.as_view(), name="admin-campaigns"),
    path(
        "admin/campaigns/<uuid:campaign_id>",
        campaign_views.CampaignView.as_view(),
        name="admin-campaign",
    ),
    path(
        "admin/campaigns/<uuid:campaign_id>/report",
        campaign_views.CampaignReportView.as_view(),
        name="admin-campaign-report",
    ),
    *[
        path(
            f"admin/campaigns/<uuid:campaign_id>/{action}",
            campaign_views.action_view(action).as_view(),
            name=f"admin-campaign-{action}",
        )
        for action in CAMPAIGN_ACTIONS
    ],
    path("admin/events", event_views.AdminEventsView.as_view(), name="admin-events"),
    path("admin/events/<uuid:event_id>", event_views.AdminEventView.as_view(), name="admin-event"),
    path(
        "admin/events/<uuid:event_id>/slots",
        event_views.EventSlotsView.as_view(),
        name="admin-event-slots",
    ),
    path(
        "admin/events/<uuid:event_id>/attendees",
        event_views.AttendeesView.as_view(),
        name="admin-event-attendees",
    ),
    path(
        "admin/events/<uuid:event_id>/attendees.csv",
        event_views.AttendeesExportView.as_view(),
        name="admin-event-attendees-csv",
    ),
    path(
        "admin/events/<uuid:event_id>/attendees/<uuid:user_id>/check-in",
        event_views.CheckInView.as_view(),
        name="admin-event-check-in",
    ),
    *[
        path(
            f"admin/events/<uuid:event_id>/{action}",
            event_views.state_view(action).as_view(),
            name=f"admin-event-{action}",
        )
        for action in EVENT_ACTIONS
    ],
    path("admin/editorial", editorial_views.AdminEditorialView.as_view(), name="admin-editorial"),
    path(
        "admin/editorial/<uuid:item_id>",
        editorial_views.AdminEditorialItemView.as_view(),
        name="admin-editorial-item",
    ),
    path(
        "admin/editorial/<uuid:item_id>/schedule",
        editorial_views.ScheduleItemView.as_view(),
        name="admin-editorial-schedule",
    ),
    path(
        "admin/editorial/<uuid:item_id>/cover",
        editorial_views.ItemCoverView.as_view(),
        name="admin-editorial-cover",
    ),
    *[
        path(
            f"admin/editorial/<uuid:item_id>/{action}",
            editorial_views.publish_view(action).as_view(),
            name=f"admin-editorial-{action}",
        )
        for action in ITEM_ACTIONS
    ],
    *[
        path(
            f"admin/editorial-comments/<uuid:comment_id>/{action}",
            editorial_views.comment_view(action).as_view(),
            name=f"admin-editorial-comment-{action}",
        )
        for action in COMMENT_ACTIONS_ITEM
    ],
    path("admin/win-submissions", editorial_views.AdminWinsView.as_view(), name="admin-wins"),
    *[
        path(
            f"admin/win-submissions/<uuid:win_id>/{decision}",
            editorial_views.win_view(decision).as_view(),
            name=f"admin-win-{decision}",
        )
        for decision in WIN_DECISIONS
    ],
    path("admin/jobs", job_views.AdminJobsView.as_view(), name="admin-jobs"),
    path("admin/jobs/settings", job_views.JobSettingsView.as_view(), name="admin-job-settings"),
    path("admin/jobs/<uuid:job_id>", job_views.AdminJobView.as_view(), name="admin-job"),
    *[
        path(
            f"admin/jobs/<uuid:job_id>/{decision}",
            job_views.review_view(decision).as_view(),
            name=f"admin-job-{decision}",
        )
        for decision in JOB_DECISIONS
    ],
    *[
        path(
            f"admin/comments/<uuid:comment_id>/{action}",
            feed_views.comment_action_view(action).as_view(),
            name=f"admin-comment-{action}",
        )
        for action in COMMENT_ACTIONS
    ],
    path("admin/reports", feed_views.ReportListView.as_view(), name="admin-reports"),
    path(
        "admin/reports/<uuid:report_id>", feed_views.ReportDetailView.as_view(), name="admin-report"
    ),
    path(
        "admin/reports/<uuid:report_id>/review",
        feed_views.ReportReviewView.as_view(),
        name="admin-report-review",
    ),
    path(
        "admin/reports/<uuid:report_id>/action",
        feed_views.ReportActionView.as_view(),
        name="admin-report-action",
    ),
    *[
        path(
            f"admin/posts/<uuid:post_id>/{action}",
            feed_views.action_view(action).as_view(),
            name=f"admin-post-{action}",
        )
        for action in POST_ACTIONS
    ],
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
