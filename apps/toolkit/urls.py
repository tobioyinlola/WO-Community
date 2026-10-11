from django.urls import include, path

urlpatterns = [
    path("", include("apps.toolkit.ventures.urls")),
    path("", include("apps.toolkit.jobs.urls")),
    path("", include("apps.toolkit.ai.urls")),
    path("", include("apps.toolkit.scoring.urls")),
    path("", include("apps.toolkit.plans.urls")),
    path("", include("apps.toolkit.forecasts.urls")),
    path("", include("apps.toolkit.decks.urls")),
]
