from django.urls import path

from apps.toolkit.advisor import views

urlpatterns = [
    path("advisor/messages", views.MessagesView.as_view(), name="tk-advisor-messages"),
    path("advisor/voice", views.VoiceTurnView.as_view(), name="tk-advisor-voice"),
    path(
        "advisor/messages/<uuid:message_id>/speech",
        views.SpeechLinkView.as_view(),
        name="tk-advisor-speech-link",
    ),
    path("advisor/speech/<str:token>", views.SpeechStreamView.as_view(), name="tk-advisor-speech"),
]
