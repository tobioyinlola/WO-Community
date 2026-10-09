from django.urls import path

from apps.accounts import auth_views, mfa_views
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
    path(
        "auth/invitations/inspect",
        auth_views.InspectInvitationView.as_view(),
        name="auth-invitation-inspect",
    ),
    path("auth/verify-email", auth_views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("auth/login", auth_views.LoginView.as_view(), name="auth-login"),
    path("auth/refresh", auth_views.RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", auth_views.LogoutView.as_view(), name="auth-logout"),
    path("auth/mfa/verify", mfa_views.MfaVerifyView.as_view(), name="auth-mfa-verify"),
    path("auth/mfa/enrol", mfa_views.MfaEnrolView.as_view(), name="auth-mfa-enrol"),
    path("auth/mfa/confirm", mfa_views.MfaConfirmView.as_view(), name="auth-mfa-confirm"),
    path("auth/mfa/step-up", mfa_views.MfaStepUpView.as_view(), name="auth-mfa-step-up"),
    path(
        "auth/mfa/recovery-codes",
        mfa_views.RecoveryCodesView.as_view(),
        name="auth-mfa-recovery-codes",
    ),
    path("auth/password/forgot", auth_views.ForgotPasswordView.as_view(), name="auth-forgot"),
    path("auth/password/reset", auth_views.ResetPasswordView.as_view(), name="auth-reset"),
]
