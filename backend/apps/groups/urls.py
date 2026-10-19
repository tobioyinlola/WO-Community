from django.urls import path

from apps.groups import views

urlpatterns = [
    path("groups", views.GroupsView.as_view(), name="groups"),
    path("groups/<uuid:group_id>", views.GroupView.as_view(), name="group"),
    path(
        "groups/<uuid:group_id>/membership", views.MembershipView.as_view(), name="group-membership"
    ),
    path("groups/<uuid:group_id>/messages", views.MessagesView.as_view(), name="group-messages"),
    path("group-messages/<uuid:message_id>", views.MessageView.as_view(), name="group-message"),
    path(
        "group-messages/<uuid:message_id>/reactions",
        views.ReactionView.as_view(),
        name="group-message-react",
    ),
]
