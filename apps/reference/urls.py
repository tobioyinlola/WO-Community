from django.urls import path

from apps.reference import views

urlpatterns = [
    path("reference/sectors", views.SectorListView.as_view(), name="reference-sectors"),
    path("reference/stages", views.StageListView.as_view(), name="reference-stages"),
    path("reference/skills", views.SkillListView.as_view(), name="reference-skills"),
    path("reference/countries", views.CountryListView.as_view(), name="reference-countries"),
]
