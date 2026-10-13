from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("me/marketing-consent", views.MarketingConsentView.as_view(), name="marketing-consent"),
    path("notifications", views.NotificationsView.as_view(), name="notifications"),
    path(
        "notifications/unread-count",
        views.UnreadCountView.as_view(),
        name="notifications-unread-count",
    ),
    path("notifications/read", views.MarkReadView.as_view(), name="notifications-read"),
    path("webhooks/email/<slug:provider>", views.EmailWebhookView.as_view(), name="email-webhook"),
    path(
        "me/notification-preferences",
        views.NotificationPreferencesView.as_view(),
        name="notification-preferences",
    ),
]
