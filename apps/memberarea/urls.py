from django.urls import path

from apps.memberarea import views

urlpatterns = [
    path("me/onboarding", views.OnboardingView.as_view(), name="onboarding"),
    path("search", views.SearchView.as_view(), name="search"),
    path("me/news/following", views.FollowingNewsView.as_view(), name="news-following"),
    path("public/sitemaps", views.FullSitemapView.as_view(), name="public-sitemaps"),
]
