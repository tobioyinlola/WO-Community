from django.urls import path

from apps.toolkit.forecasts import views

base = "ventures/<uuid:venture_id>/forecast"

urlpatterns = [
    path("forecast-templates", views.TemplatesView.as_view(), name="tk-forecast-templates"),
    path(base, views.ForecastView.as_view(), name="tk-forecast"),
    path(f"{base}/result", views.ResultView.as_view(), name="tk-forecast-result"),
    path(f"{base}/scenarios", views.ScenariosView.as_view(), name="tk-forecast-scenarios"),
    path(f"{base}/sensitivity", views.SensitivityView.as_view(), name="tk-forecast-sensitivity"),
    path(f"{base}/suggest", views.SuggestView.as_view(), name="tk-forecast-suggest"),
    path(f"{base}/export", views.ExportView.as_view(), name="tk-forecast-export"),
    path(f"{base}/versions", views.VersionsView.as_view(), name="tk-forecast-versions"),
    path(
        f"{base}/versions/<int:version>/restore",
        views.RestoreView.as_view(),
        name="tk-forecast-restore",
    ),
]
