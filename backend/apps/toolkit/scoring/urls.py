from django.urls import path

from apps.toolkit.scoring import views

urlpatterns = [
    path("ventures/<uuid:venture_id>/score", views.ScoreStartView.as_view(), name="tk-score"),
    path(
        "ventures/<uuid:venture_id>/score/latest",
        views.ScoreLatestView.as_view(),
        name="tk-score-latest",
    ),
    path(
        "ventures/<uuid:venture_id>/score/history",
        views.ScoreHistoryView.as_view(),
        name="tk-score-history",
    ),
    path(
        "ventures/<uuid:venture_id>/score/summary",
        views.ScoreSummaryView.as_view(),
        name="tk-score-summary",
    ),
]
