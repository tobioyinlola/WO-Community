from django.urls import include, path

from apps.core.views import HealthLiveView, HealthReadyView, SchemaView

urlpatterns = [
    path("health/live", HealthLiveView.as_view(), name="health-live"),
    path("health/ready", HealthReadyView.as_view(), name="health-ready"),
    path("api/v1/schema/", SchemaView.as_view(), name="schema"),
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/", include("apps.analytics.urls")),
    path("api/v1/", include("apps.reference.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.uploads.urls")),
    path("api/v1/", include("apps.profiles.urls")),
    path("api/v1/", include("apps.startups.urls")),
    path("api/v1/", include("apps.directory.urls")),
    path("api/v1/", include("apps.memberarea.urls")),
    path("api/v1/", include("apps.feed.urls")),
    path("api/v1/", include("apps.jobs.urls")),
    path("api/v1/", include("apps.editorial.urls")),
    path("api/v1/", include("apps.events.urls")),
    path("api/v1/", include("apps.campaigns.urls")),
    path("api/v1/", include("apps.adminconsole.urls")),
]
