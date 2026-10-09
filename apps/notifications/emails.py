"""Plain text transactional emails sent by the accounts module."""

from django.conf import settings

from apps.integrations.email import EmailMessage, get_email_adapter


def _send(to: str, subject: str, body: str) -> None:
    get_email_adapter().send(EmailMessage(to=to, subject=subject, text_body=body))


def send_verification(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/verify-email?token={token}"
    _send(
        to,
        "Confirm your email address",
        "Welcome to WO Community.\n\n"
        f"Confirm your email address to continue:\n{link}\n\n"
        "The link expires in 24 hours. If you did not register, you can ignore this message.",
    )


def send_already_registered(to: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/login"
    reset = f"{settings.FRONTEND_BASE_URL}/forgot-password"
    _send(
        to,
        "You already have a WO Community account",
        "Someone tried to register with this address, but an account already exists.\n\n"
        f"Log in: {link}\nForgot your password: {reset}\n\n"
        "If this was not you, no action is needed.",
    )


def send_approved(to: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/login"
    _send(
        to,
        "Your WO Community account is approved",
        f"Welcome aboard. Your account has been approved and you can now log in:\n{link}",
    )


def send_rejected(to: str, reason: str) -> None:
    _send(
        to,
        "Your WO Community registration",
        "We could not approve your registration at this time.\n\n"
        f"Reason: {reason}\n\n"
        "If you think this is a mistake, reply to this email and our team will look again.",
    )


def send_password_reset(to: str, token: str) -> None:
    link = f"{settings.FRONTEND_BASE_URL}/reset-password?token={token}"
    _send(
        to,
        "Reset your password",
        f"Use this link to choose a new password:\n{link}\n\n"
        "The link expires in 1 hour. If you did not ask for this, you can ignore this message.",
    )
