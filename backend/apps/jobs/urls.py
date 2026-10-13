from django.urls import path

from apps.jobs import views

urlpatterns = [
    path("jobs", views.JobsView.as_view(), name="jobs"),
    path("jobs/<uuid:job_id>", views.JobView.as_view(), name="job"),
    path("jobs/<uuid:job_id>/renew", views.RenewJobView.as_view(), name="job-renew"),
    path("jobs/<uuid:job_id>/close", views.CloseJobView.as_view(), name="job-close"),
    path("jobs/<uuid:job_id>/save", views.SaveJobView.as_view(), name="job-save"),
    path("me/jobs", views.MyJobsView.as_view(), name="my-jobs"),
    path("me/saved-jobs", views.SavedJobsView.as_view(), name="saved-jobs"),
    path("job-alerts", views.AlertsView.as_view(), name="job-alerts"),
    path("job-alerts/<uuid:alert_id>", views.AlertView.as_view(), name="job-alert"),
    path("public/jobs", views.PublicJobsView.as_view(), name="public-jobs"),
    path("public/jobs/sitemap", views.PublicJobsSitemapView.as_view(), name="public-jobs-sitemap"),
    path("public/jobs/<slug:slug>", views.PublicJobView.as_view(), name="public-job"),
]
