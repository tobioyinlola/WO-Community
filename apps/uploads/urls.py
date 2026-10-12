from django.urls import path

from apps.uploads import views

urlpatterns = [
    path("uploads", views.UploadCreateView.as_view(), name="upload-create"),
    path("uploads/<uuid:upload_id>", views.UploadDetailView.as_view(), name="upload-detail"),
    path(
        "uploads/<uuid:upload_id>/complete",
        views.UploadCompleteView.as_view(),
        name="upload-complete",
    ),
]
