from django.urls import path

from apps.toolkit.partner import views

b = "ventures/<uuid:venture_id>/partner"

urlpatterns = [
    path(f"{b}/conversations", views.ConversationsView.as_view(), name="tk-conversations"),
    path(
        f"{b}/conversations/<uuid:conversation_id>",
        views.ConversationView.as_view(),
        name="tk-conversation",
    ),
    path(
        f"{b}/conversations/<uuid:conversation_id>/messages",
        views.MessagesView.as_view(),
        name="tk-messages",
    ),
    path(
        f"{b}/change-sets/<uuid:change_set_id>/apply",
        views.ChangeApplyView.as_view(),
        name="tk-change-apply",
    ),
    path(
        f"{b}/change-sets/<uuid:change_set_id>/undo",
        views.ChangeUndoView.as_view(),
        name="tk-change-undo",
    ),
    path(
        f"{b}/change-sets/<uuid:change_set_id>/dismiss",
        views.ChangeDismissView.as_view(),
        name="tk-change-dismiss",
    ),
    path(f"{b}/decisions", views.DecisionsView.as_view(), name="tk-decisions"),
    path(f"{b}/decisions/<uuid:decision_id>", views.DecisionView.as_view(), name="tk-decision"),
    path(f"{b}/nudges", views.NudgesView.as_view(), name="tk-nudges"),
    path(f"{b}/nudges/<uuid:nudge_id>/read", views.NudgeReadView.as_view(), name="tk-nudge-read"),
    path(f"{b}/mentors", views.MentorSuggestionsView.as_view(), name="tk-partner-mentors"),
]
