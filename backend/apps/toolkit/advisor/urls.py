from django.urls import path

from apps.toolkit.advisor import views

urlpatterns = [
    path("advisor/messages", views.MessagesView.as_view(), name="tk-advisor-messages"),
]
