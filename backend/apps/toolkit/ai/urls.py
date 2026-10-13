from django.urls import path

from apps.toolkit.ai import views

urlpatterns = [
    path(
        "ventures/<uuid:venture_id>/profile/suggest",
        views.SuggestView.as_view(),
        name="tk-profile-suggest",
    ),
    path(
        "ventures/<uuid:venture_id>/profile/fill-from-text",
        views.FillFromTextView.as_view(),
        name="tk-profile-fill",
    ),
]
