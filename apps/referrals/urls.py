from django.urls import path

from apps.referrals import views

urlpatterns = [
    path("members/search-referrer", views.ReferrerSearchView.as_view(), name="referrer-search"),
    path("members/referrer-by-code", views.ReferrerByCodeView.as_view(), name="referrer-by-code"),
    path("me/referrals", views.MyReferralsView.as_view(), name="my-referrals"),
]
