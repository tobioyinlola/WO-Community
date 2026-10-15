from django.urls import path

from apps.toolkit.admin_api import views

urlpatterns = [
    path("admin/deck-templates", views.DeckTemplatesView.as_view(), name="tk-admin-decks"),
    path(
        "admin/prototype-templates",
        views.PrototypeTemplatesView.as_view(),
        name="tk-admin-prototypes",
    ),
    path("admin/plan-sections", views.PlanSectionsView.as_view(), name="tk-admin-sections"),
    path(
        "admin/plan-sections/<int:number>",
        views.PlanSectionView.as_view(),
        name="tk-admin-section",
    ),
    path("admin/score-rubrics", views.RubricsView.as_view(), name="tk-admin-rubrics"),
    path(
        "admin/score-rubrics/<int:version>/activate",
        views.RubricActivateView.as_view(),
        name="tk-admin-rubric-activate",
    ),
    path("admin/usage", views.UsageView.as_view(), name="tk-admin-usage"),
    path("admin/usage.csv", views.UsageCsvView.as_view(), name="tk-admin-usage-csv"),
    path("admin/quality", views.QualityView.as_view(), name="tk-admin-quality"),
    path("admin/settings", views.SettingsView.as_view(), name="tk-admin-settings"),
    path("admin/ventures", views.VenturesView.as_view(), name="tk-admin-ventures"),
]
