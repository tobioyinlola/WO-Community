from django.urls import path

from apps.toolkit.plans import views

base = "ventures/<uuid:venture_id>/plan"

urlpatterns = [
    path(base, views.PlanView.as_view(), name="tk-plan"),
    path(f"{base}/generate", views.PlanStartView.as_view(), name="tk-plan-generate"),
    path(f"{base}/export", views.PlanExportView.as_view(), name="tk-plan-export"),
    path(f"{base}/readiness", views.PlanReadinessView.as_view(), name="tk-plan-readiness"),
    path(f"{base}/versions", views.PlanVersionsView.as_view(), name="tk-plan-versions"),
    path(
        f"{base}/versions/<int:version>/restore",
        views.PlanVersionRestoreView.as_view(),
        name="tk-plan-restore",
    ),
    path(
        f"{base}/sections/<int:number>",
        views.PlanSectionView.as_view(),
        name="tk-plan-section",
    ),
    path(
        f"{base}/sections/<int:number>/assist",
        views.PlanSectionAssistView.as_view(),
        name="tk-plan-assist",
    ),
]
