from django.urls import path

from apps.analytics import views

urlpatterns = [
    path("analytics/events", views.EventIngestView.as_view(), name="analytics-events"),
    path("me/analytics-preferences", views.MyPreferenceView.as_view(), name="analytics-preference"),
]
