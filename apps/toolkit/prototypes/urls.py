from django.urls import path

from apps.toolkit.prototypes import views

v = "ventures/<uuid:venture_id>/prototypes"
p = f"{v}/<uuid:prototype_id>"

urlpatterns = [
    path("prototype-components", views.ComponentsView.as_view(), name="tk-proto-components"),
    path("prototype-templates", views.TemplatesView.as_view(), name="tk-proto-templates"),
    path(v, views.PrototypesView.as_view(), name="tk-prototypes"),
    path(f"{v}/generate", views.GenerateView.as_view(), name="tk-proto-generate"),
    path(p, views.PrototypeView.as_view(), name="tk-prototype"),
    path(f"{p}/duplicate", views.DuplicateView.as_view(), name="tk-proto-duplicate"),
    path(f"{p}/versions", views.VersionsView.as_view(), name="tk-proto-versions"),
    path(
        f"{p}/versions/<int:version>/restore",
        views.RestoreView.as_view(),
        name="tk-proto-restore",
    ),
]
