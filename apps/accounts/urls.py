from django.urls import path

from apps.accounts import auth_views
from apps.accounts.views import MeView

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("me/sessions", auth_views.SessionListView.as_view(), name="sessions"),
    path(
        "me/sessions/<uuid:session_id>",
        auth_views.SessionDetailView.as_view(),
        name="session-detail",
    ),
    path("auth/register", auth_views.RegisterView.as_view(), name="auth-register"),
    path("auth/verify-email", auth_views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("auth/login", auth_views.LoginView.as_view(), name="auth-login"),
    path("auth/refresh", auth_views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="auth-logout"),
    path("auth/password/forgot", auth_views.ForgotPasswordView.as_view(), name="auth-forgot"),
    path("auth/password/reset", auth_views.ResetPasswordView.as_view(), name="auth-reset"),
]
