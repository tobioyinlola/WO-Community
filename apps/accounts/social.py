"""Sign in, and sign up, with a Google account.

The browser gets an ID token from Google and sends it here. A verified Google address is proof
of the mailbox, exactly as an invitation link or a verification email is, so it can sign in an
existing member, or start a new registration that still waits for an admin like any other.
"""

from dataclasses import dataclass
from typing import Any

import structlog
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import exceptions

from apps.accounts import events, invitations, services, sessions
from apps.accounts.models import BLOCKED_STATUSES, SocialIdentity, User
from apps.analytics import services as analytics
from apps.audit import services as audit
from apps.core import events as domain_events
from apps.core.identity import (
    IdentityProviderUnavailable,
    IdTokenVerifier,
    InvalidIdToken,
    VerifiedIdentity,
)

logger = structlog.get_logger(__name__)

PROVIDER = "google"


class GoogleSignInDisabled(exceptions.NotFound):
    default_code = "google_sign_in_disabled"
    default_detail = "Google sign-in is not available."


class InvalidGoogleToken(exceptions.APIException):
    status_code = 401
    default_code = "invalid_google_token"
    default_detail = "Google sign-in failed. Try again."


class GoogleEmailUnverified(exceptions.APIException):
    status_code = 403
    default_code = "google_email_unverified"
    default_detail = "Verify the email address on your Google account first."


class GoogleUnavailable(exceptions.APIException):
    status_code = 503
    default_code = "google_unavailable"
    default_detail = "Google could not be reached. Try again in a moment."


class RegistrationRequired(Exception):
    """The Google account is new to us: collect the sign-up details and send them with the token."""

    def __init__(self, identity: VerifiedIdentity) -> None:
        self.email = services.normalise_email(identity.email)
        self.name = identity.name


@dataclass(frozen=True)
class GoogleOutcome:
    result: services.LoginResult | services.MfaChallenge
    created: bool


def _verifier() -> IdTokenVerifier:
    verifier: IdTokenVerifier = import_string(settings.GOOGLE_TOKEN_VERIFIER)()
    return verifier


def _verify(id_token: str, nonce: str) -> VerifiedIdentity:
    if not settings.GOOGLE_CLIENT_ID:
        raise GoogleSignInDisabled()
    try:
        identity = _verifier().verify(id_token, nonce=nonce)
    except InvalidIdToken:
        raise InvalidGoogleToken() from None
    except IdentityProviderUnavailable:
        raise GoogleUnavailable() from None
    if not identity.email_verified:
        raise GoogleEmailUnverified()
    return identity


def _link(user: User, identity: VerifiedIdentity, ip: str) -> None:
    """Attach the Google login to an account that already has this address.

    If the address was never confirmed, whoever created the account may not own the mailbox, so
    the password they chose is discarded and every session they might hold is ended.
    """
    SocialIdentity.objects.create(user=user, provider=PROVIDER, subject=identity.subject)
    hijackable = user.email_verified_at is None
    if hijackable:
        user.email_verified_at = timezone.now()
        user.set_unusable_password()
        user.save(update_fields=["email_verified_at", "password", "updated_at"])
        sessions.revoke_all(user, "google_link_unverified")
    audit.record(
        actor=user,
        action="auth.google_linked",
        target_type="user",
        target_id=user.pk,
        after={"password_discarded": hijackable},
        ip=ip,
    )


def _register(identity: VerifiedIdentity, registration: dict[str, Any], ip: str) -> User:
    address = services.normalise_email(identity.email)
    token = registration.get("invitation_token", "")
    invitation = invitations.lock_for_registration(token, address) if token else None
    if invitation is not None:
        user = services.create_invited_user(address, None, invitation)
    else:
        # Pending: an admin still has to approve, like any other self-registration.
        user = User.objects.create_user(address, None, email_verified_at=timezone.now())
    SocialIdentity.objects.create(user=user, provider=PROVIDER, subject=identity.subject)
    services.record_consents(user, registration["consents"], ip)
    anonymous_id = registration.get("anonymous_id")
    if anonymous_id is not None:
        analytics.identify(anonymous_id, user.pk)
    domain_events.publish(
        events.SignupDetailsSubmitted(user_id=str(user.pk), details=registration["signup"])
    )
    analytics.track("email_verified", actor_id=user.pk)
    if invitation is not None:
        invitations.mark_registered(invitation, user)
        domain_events.publish(events.MemberApproved(user_id=str(user.pk)))
        analytics.track(
            "invitation_registered", actor_id=user.pk, properties={"role": invitation.role}
        )
        analytics.track(
            "member_approved",
            actor_id=user.pk,
            properties={"approval_source": "invitation", "time_to_decision_hours": 0},
        )
    audit.record(
        actor=user,
        action="auth.registered",
        target_type="user",
        target_id=user.pk,
        after={"method": PROVIDER, **({"approval_source": "invitation"} if invitation else {})},
        ip=ip,
    )
    return user


def sign_in_with_google(
    *,
    id_token: str,
    nonce: str = "",
    registration: dict[str, Any] | None = None,
    ip: str,
    user_agent: str,
) -> GoogleOutcome:
    """Sign in with a Google ID token, linking or creating the account as needed.

    Raises ``RegistrationRequired`` when the person is new and sent no sign-up details.
    """
    identity = _verify(id_token, nonce)
    address = services.normalise_email(identity.email)
    created = False
    try:
        with transaction.atomic():
            link = (
                SocialIdentity.objects.select_related("user")
                .filter(provider=PROVIDER, subject=identity.subject)
                .first()
            )
            if link is not None:
                user = link.user
            else:
                existing = User.objects.select_for_update().filter(email__iexact=address).first()
                if existing is not None:
                    user = existing
                    if user.status not in BLOCKED_STATUSES:
                        _link(user, identity, ip)
                elif registration is None:
                    raise RegistrationRequired(identity)
                else:
                    user = _register(identity, registration, ip)
                    created = True
    except IntegrityError:
        logger.info("google_sign_in_race")
        raise InvalidGoogleToken() from None
    if user.status in BLOCKED_STATUSES:
        audit.record(
            actor=None,
            action="auth.login_failed",
            target_type="email_hash",
            target_id=services.hash_address(address),
            after={"method": PROVIDER},
            ip=ip,
            user_agent=user_agent,
        )
        raise services.InvalidCredentials()
    return GoogleOutcome(
        services.begin_session(user, ip=ip, user_agent=user_agent, method=PROVIDER), created
    )
