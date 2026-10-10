from django.urls import path

from apps.memberarea import views

urlpatterns = [
    path("me/onboarding", views.OnboardingView.as_view(), name="onboarding"),
    path("search", views.SearchView.as_view(), name="search"),
]
