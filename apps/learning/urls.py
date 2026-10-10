from django.urls import path

from apps.learning import views

urlpatterns = [
    path("courses", views.CoursesView.as_view(), name="courses"),
    path("courses/categories", views.CategoriesView.as_view(), name="course-categories"),
    path("courses/<uuid:course_id>", views.CourseView.as_view(), name="course"),
    path("courses/<uuid:course_id>/enrol", views.EnrolView.as_view(), name="course-enrol"),
    path("courses/<uuid:course_id>/rating", views.RatingView.as_view(), name="course-rating"),
    path("me/courses", views.MyCoursesView.as_view(), name="my-courses"),
    path("lessons/<uuid:lesson_id>", views.LessonView.as_view(), name="lesson"),
    path(
        "lessons/<uuid:lesson_id>/progress",
        views.LessonProgressView.as_view(),
        name="lesson-progress",
    ),
    path("certificates", views.CertificatesView.as_view(), name="certificates"),
    path("certificates/<uuid:certificate_id>", views.CertificateView.as_view(), name="certificate"),
    path(
        "certificates/<uuid:certificate_id>/pdf",
        views.CertificatePdfView.as_view(),
        name="certificate-pdf",
    ),
    path("public/courses", views.PublicCoursesView.as_view(), name="public-courses"),
    path("public/courses/<slug:slug>", views.PublicCourseView.as_view(), name="public-course"),
    path(
        "public/certificates/<str:code>",
        views.VerifyCertificateView.as_view(),
        name="verify-certificate",
    ),
]
