from django.urls import path

from apps.toolkit.decks import views

v = "ventures/<uuid:venture_id>/decks"
d = f"{v}/<uuid:deck_id>"

urlpatterns = [
    path("deck-templates", views.TemplatesView.as_view(), name="tk-deck-templates"),
    path(v, views.DecksView.as_view(), name="tk-decks"),
    path(d, views.DeckView.as_view(), name="tk-deck"),
    path(f"{d}/shown", views.ShownView.as_view(), name="tk-deck-shown"),
    path(f"{d}/check", views.CheckView.as_view(), name="tk-deck-check"),
    path(f"{d}/assist", views.AssistView.as_view(), name="tk-deck-assist"),
    path(f"{d}/export", views.ExportView.as_view(), name="tk-deck-export"),
    path(f"{d}/versions", views.VersionsView.as_view(), name="tk-deck-versions"),
    path(
        f"{d}/versions/<int:version>/restore",
        views.RestoreView.as_view(),
        name="tk-deck-restore",
    ),
    path(f"{d}/assets", views.AssetsView.as_view(), name="tk-deck-assets"),
    path(f"{d}/assets/<uuid:asset_id>", views.AssetView.as_view(), name="tk-deck-asset"),
]
