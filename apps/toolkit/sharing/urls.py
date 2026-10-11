from django.urls import path

from apps.toolkit.sharing import views

urlpatterns = [
    path("ventures/<uuid:venture_id>/shares", views.SharesView.as_view(), name="tk-shares"),
    path(
        "ventures/<uuid:venture_id>/shares/<uuid:share_id>",
        views.ShareView.as_view(),
        name="tk-share",
    ),
    path("public/share/<str:token>", views.PublicShareView.as_view(), name="tk-public-share"),
]
