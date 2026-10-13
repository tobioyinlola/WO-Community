from django.urls import path

from apps.directory import views

urlpatterns = [
    path("public/startups", views.StartupListView.as_view(), name="public-startups"),
    path("public/startups/<slug:slug>", views.StartupDetailView.as_view(), name="public-startup"),
    path("public/founders", views.FounderListView.as_view(), name="public-founders"),
    path("public/founders/<slug:slug>", views.FounderDetailView.as_view(), name="public-founder"),
    path("public/sitemap", views.SitemapView.as_view(), name="public-sitemap"),
]
