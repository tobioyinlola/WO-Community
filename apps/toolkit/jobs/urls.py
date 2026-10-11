from django.urls import path

from apps.toolkit.jobs import views

urlpatterns = [
    path("jobs/<uuid:job_id>", views.JobView.as_view(), name="tk-job"),
    path("jobs/<uuid:job_id>/cancel", views.JobCancelView.as_view(), name="tk-job-cancel"),
]
