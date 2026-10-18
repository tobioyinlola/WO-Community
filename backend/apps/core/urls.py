from django.urls import path

from apps.core.sharing_views import PublicShareCardView
from apps.core.views import PingView

urlpatterns = [
    path("ping", PingView.as_view(), name="ping"),
    path(
        "public/share/<slug:kind>/<str:ref>",
        PublicShareCardView.as_view(),
        name="public-share-card",
    ),
]
