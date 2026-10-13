from django.urls import path

from apps.core.views import PingView

urlpatterns = [
    path("ping", PingView.as_view(), name="ping"),
]
