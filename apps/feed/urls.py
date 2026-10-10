from django.urls import path

from apps.feed import views

urlpatterns = [
    path("posts", views.FeedView.as_view(), name="feed"),
    path("posts/<uuid:post_id>", views.PostView.as_view(), name="feed-post"),
    path("posts/<uuid:post_id>/comments", views.PostCommentsView.as_view(), name="feed-comments"),
    path("posts/<uuid:target_id>/reactions", views.ReactionsView.as_view(), name="feed-react"),
    path(
        "posts/<uuid:target_id>/reactions/<slug:kind>",
        views.ReactionDeleteView.as_view(),
        name="feed-unreact",
    ),
    path("comments/<uuid:comment_id>", views.CommentView.as_view(), name="feed-comment"),
    path(
        "comments/<uuid:target_id>/reactions",
        views.CommentReactionsView.as_view(),
        name="feed-comment-react",
    ),
    path(
        "comments/<uuid:target_id>/reactions/<slug:kind>",
        views.CommentReactionDeleteView.as_view(),
        name="feed-comment-unreact",
    ),
]
