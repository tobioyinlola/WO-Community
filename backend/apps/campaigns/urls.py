from django.urls import path

from apps.campaigns import views

urlpatterns = [
    path("unsubscribe", views.UnsubscribeView.as_view(), name="unsubscribe"),
    path("newsletter/subscribe", views.NewsletterSignupView.as_view(), name="newsletter-subscribe"),
    path("newsletter/confirm", views.NewsletterConfirmView.as_view(), name="newsletter-confirm"),
    path(
        "newsletter/unsubscribe",
        views.NewsletterUnsubscribeView.as_view(),
        name="newsletter-unsubscribe",
    ),
]
