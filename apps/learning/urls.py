from django.urls import path

from apps.learning import lms_views, views

urlpatterns = [
    path("courses", views.CoursesView.as_view(), name="courses"),
    path("courses/categories", views.CategoriesView.as_view(), name="course-categories"),
    path("courses/<uuid:course_id>", views.CourseView.as_view(), name="course"),
    path("courses/<uuid:course_id>/enrol", views.EnrolView.as_view(), name="course-enrol"),
    path("courses/<uuid:course_id>/rating", views.RatingView.as_view(), name="course-rating"),
    path("courses/page/<str:ref>", lms_views.CoursePageView.as_view(), name="course-page"),
    path(
        "courses/<uuid:course_id>/reviews", lms_views.ReviewsView.as_view(), name="course-reviews"
    ),
    path(
        "courses/<uuid:course_id>/wishlist",
        lms_views.WishlistView.as_view(),
        name="course-wishlist",
    ),
    path(
        "courses/<uuid:course_id>/request-access",
        lms_views.AccessRequestView.as_view(),
        name="course-request-access",
    ),
    path(
        "courses/<uuid:course_id>/announcements",
        lms_views.AnnouncementsView.as_view(),
        name="course-announcements",
    ),
    path("me/learning", lms_views.ShelfView.as_view(), name="my-learning"),
    path("me/courses", views.MyCoursesView.as_view(), name="my-courses"),
    path(
        "lessons/<uuid:lesson_id>/questions",
        lms_views.QuestionsView.as_view(),
        name="lesson-questions",
    ),
    path("lessons/<uuid:lesson_id>/notes", lms_views.NotesView.as_view(), name="lesson-notes"),
    path(
        "questions/<uuid:question_id>/answers",
        lms_views.AnswersView.as_view(),
        name="question-answers",
    ),
    path("notes/<uuid:note_id>", lms_views.NoteView.as_view(), name="note"),
    path("lessons/<uuid:lesson_id>", views.LessonView.as_view(), name="lesson"),
    path("lessons/<uuid:lesson_id>/file", views.LessonFileView.as_view(), name="lesson-file"),
    path(
        "lessons/<uuid:lesson_id>/progress",
        views.LessonProgressView.as_view(),
        name="lesson-progress",
    ),
    path("certificates", views.CertificatesView.as_view(), name="certificates"),
    path("me/certificates", views.CertificatesView.as_view(), name="my-certificates"),
    path("certificates/<uuid:certificate_id>", views.CertificateView.as_view(), name="certificate"),
    path(
        "members/<uuid:user_id>/certificates",
        views.MemberCertificatesView.as_view(),
        name="member-certificates",
    ),
    path(
        "certificates/<uuid:certificate_id>/download",
        views.CertificateDownloadView.as_view(),
        name="certificate-download",
    ),
    path("public/courses", views.PublicCoursesView.as_view(), name="public-courses"),
    path("public/courses/<slug:slug>", views.PublicCourseView.as_view(), name="public-course"),
    path(
        "public/certificates/<str:code>",
        views.VerifyCertificateView.as_view(),
        name="verify-certificate",
    ),
]
