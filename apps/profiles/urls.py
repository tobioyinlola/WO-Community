from django.urls import path

from apps.profiles import views

urlpatterns = [
    path("me/profile", views.MyProfileView.as_view(), name="my-profile"),
    path("me/visibility", views.MyVisibilityView.as_view(), name="my-visibility"),
    path("members/<uuid:user_id>", views.MemberProfileView.as_view(), name="member-profile"),
]
