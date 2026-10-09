from django.urls import include, path

from apps.core.views import HealthLiveView, HealthReadyView, SchemaView

urlpatterns = [
    path("health/live", HealthLiveView.as_view(), name="health-live"),
    path("health/ready", HealthReadyView.as_view(), name="health-ready"),
    path("api/v1/schema/", SchemaView.as_view(), name="schema"),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.accounts.urls")),
]
