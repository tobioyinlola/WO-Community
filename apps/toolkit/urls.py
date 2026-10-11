from django.urls import include, path

urlpatterns = [
    path("", include("apps.toolkit.ventures.urls")),
    path("", include("apps.toolkit.jobs.urls")),
    path("", include("apps.toolkit.ai.urls")),
]
