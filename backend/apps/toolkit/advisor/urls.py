from django.urls import path

from apps.toolkit.advisor import views

urlpatterns = [
    path("advisor/messages", views.MessagesView.as_view(), name="tk-advisor-messages"),
    path("advisor/transcribe", views.TranscribeView.as_view(), name="tk-advisor-transcribe"),
    path(
        "advisor/messages/<uuid:message_id>/speech",
        views.SpeechView.as_view(),
        name="tk-advisor-speech",
    ),
]
