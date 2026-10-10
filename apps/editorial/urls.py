from django.urls import path

from apps.editorial import views

urlpatterns = [
    path("editorial", views.EditorialListView.as_view(), name="editorial"),
    path("editorial/<uuid:item_id>", views.EditorialItemView.as_view(), name="editorial-item"),
    path(
        "editorial/<uuid:item_id>/comments",
        views.ItemCommentsView.as_view(),
        name="editorial-comments",
    ),
    path(
        "editorial/<uuid:item_id>/reactions",
        views.ItemReactionsView.as_view(),
        name="editorial-react",
    ),
    path(
        "editorial/<uuid:item_id>/reactions/<slug:kind>",
        views.ItemReactionDeleteView.as_view(),
        name="editorial-unreact",
    ),
    path(
        "editorial-comments/<uuid:comment_id>",
        views.ItemCommentView.as_view(),
        name="editorial-comment",
    ),
    path("banners", views.BannersView.as_view(), name="banners"),
    path("win-submissions", views.WinSubmissionsView.as_view(), name="win-submissions"),
    path("public/news", views.PublicNewsView.as_view(), name="public-news"),
    path("public/news/<slug:slug>", views.PublicNewsItemView.as_view(), name="public-news-item"),
]
