from django.urls import path

from apps.toolkit.jobs import views

urlpatterns = [
    path("jobs/<uuid:job_id>", views.JobView.as_view(), name="tk-job"),
    path("exports/<uuid:export_id>", views.ExportFileView.as_view(), name="tk-export"),
    path("jobs/<uuid:job_id>/cancel", views.JobCancelView.as_view(), name="tk-job-cancel"),
]
