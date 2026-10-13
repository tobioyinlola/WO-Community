from django.urls import path

from apps.globalsearch import views

urlpatterns = [
    path("search/recents", views.RecentSearchesView.as_view(), name="search-recents"),
]
