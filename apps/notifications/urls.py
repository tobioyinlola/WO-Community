from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("notifications", views.NotificationsView.as_view(), name="notifications"),
    path("notifications/read", views.MarkReadView.as_view(), name="notifications-read"),
    path("webhooks/email/<slug:provider>", views.EmailWebhookView.as_view(), name="email-webhook"),
    path(
        "me/notification-preferences",
        views.NotificationPreferencesView.as_view(),
        name="notification-preferences",
    ),
]
