from django.urls import path

from apps.notifications import views

urlpatterns = [
    path("webhooks/email/<slug:provider>", views.EmailWebhookView.as_view(), name="email-webhook"),
]
