from django.urls import path

from apps.campaigns import views

urlpatterns = [
    path("unsubscribe", views.UnsubscribeView.as_view(), name="unsubscribe"),
]
