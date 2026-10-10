from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("webhooks/email/<slug:provider>", views.EmailWebhookView.as_view(), name="email-webhook"),
    path(
        "me/notification-preferences",
        views.NotificationPreferencesView.as_view(),
        name="notification-preferences",
    ),
]
