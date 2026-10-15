from typing import Any

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts import referrals
from apps.accounts.models import RefreshTokenFamily, User
from apps.core.serializers import StrictSerializer
from apps.core.text import clean_url, plain
from apps.reference import selectors as reference


def validate_new_password(password: str, email: str = "") -> str:
    try:
        password_validation.validate_password(password, user=User(email=email))
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc
    return password


def https_link(value: str, *, hosts: tuple[str, ...] = ()) -> str:
    """A link as people type it ("acme.com", "linkedin.com/in/ada"), made a full https:// link."""
    value = value.strip()
    if value and "://" not in value:
        value = f"https://{value}"
    elif value.startswith("http://"):
        value = "https://" + value[len("http://") :]
    return clean_url(value, hosts=hosts)


class SignupProfileSerializer(StrictSerializer):
    full_name = serializers.CharField(min_length=2, max_length=120)
    country = serializers.CharField(min_length=2, max_length=2)
    city = serializers.CharField(min_length=1, max_length=100)
    linkedin_url = serializers.CharField(
        max_length=300,
        help_text="Their LinkedIn profile. Admins approve applications only with one.",
    )

    def validate_full_name(self, value: str) -> str:
        return _plain_required(value)

    def validate_linkedin_url(self, value: str) -> str:
        link = https_link(value, hosts=("linkedin.com",))
        if not link:
            raise serializers.ValidationError("Add your LinkedIn profile link.")
        return link

    def validate_city(self, value: str) -> str:
        return _plain_required(value)

    def validate_country(self, value: str) -> str:
        code = value.upper()
        if not reference.is_country(code):
            raise serializers.ValidationError("Choose a country from the list.")
        return code


class RegisterProfileSerializer(SignupProfileSerializer):
    """Country and city may be left out here; the service asks for them unless an admin invitation
    is used, as staff join to run the console and have no founder profile to fill."""

    country = serializers.CharField(min_length=2, max_length=2, required=False, allow_blank=True)
    city = serializers.CharField(min_length=1, max_length=100, required=False, allow_blank=True)
    linkedin_url = serializers.CharField(max_length=300, required=False, allow_blank=True)

    def validate_city(self, value: str) -> str:
        return _plain_required(value) if value else value

    def validate_linkedin_url(self, value: str) -> str:
        return super().validate_linkedin_url(value) if value.strip() else ""

    def validate_country(self, value: str) -> str:
        return super().validate_country(value) if value else value


class SignupStartupSerializer(StrictSerializer):
    name = serializers.CharField(min_length=1, max_length=120)
    country = serializers.CharField(min_length=2, max_length=2)
    city = serializers.CharField(min_length=1, max_length=100)
    sector = serializers.CharField(max_length=80)
    stage = serializers.CharField(max_length=80)
    pitch = serializers.CharField(min_length=1, max_length=160)
    website_url = serializers.CharField(max_length=300, help_text="The company website.")

    def validate_name(self, value: str) -> str:
        return _plain_required(value)

    def validate_website_url(self, value: str) -> str:
        link = https_link(value)
        if not link:
            raise serializers.ValidationError("Add your company website.")
        return link

    def validate_city(self, value: str) -> str:
        return _plain_required(value)

    def validate_pitch(self, value: str) -> str:
        return _plain_required(value)

    def validate_country(self, value: str) -> str:
        code = value.upper()
        if not reference.is_country(code):
            raise serializers.ValidationError("Choose a country from the list.")
        return code

    def validate_sector(self, value: str) -> str:
        if reference.get_sector(value) is None:
            raise serializers.ValidationError("Choose a sector from the list.")
        return value

    def validate_stage(self, value: str) -> str:
        if reference.get_stage(value) is None:
            raise serializers.ValidationError("Choose a stage from the list.")
        return value


def _plain_required(value: str) -> str:
    cleaned = plain(value)
    if not cleaned:
        raise serializers.ValidationError("This field may not be blank.")
    return cleaned


class ReferralInputSerializer(StrictSerializer):
    """How the person heard of us. Every part is optional; a wrong entry never blocks sign up."""

    kind = serializers.ChoiceField(choices=referrals.SOURCES, required=False, allow_blank=True)
    detail = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=referrals.DETAIL_MAX,
        help_text="Which platform, event or organisation; or a member's name when they could not "
        "be found in the search.",
    )
    referred_by = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="The member who brought them, chosen from the search. Only with source `member`.",
    )
    code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=12,
        help_text="The code in the referral link they opened, if any.",
    )


class RegisterSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    accepted_terms = serializers.BooleanField()
    accepted_privacy = serializers.BooleanField()
    accepted_conduct = serializers.BooleanField()
    marketing_consent = serializers.BooleanField(required=False, default=False)
    also_mentor = serializers.BooleanField(
        required=False,
        default=False,
        help_text="I am also a mentor. Only records interest; an admin still approves.",
    )
    profile = RegisterProfileSerializer()
    startup = SignupStartupSerializer(
        required=False, help_text="Required, except with an invitation to an admin role."
    )
    anonymous_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    referral = ReferralInputSerializer(required=False, default=dict)
    invitation_token = serializers.CharField(
        required=False, allow_blank=True, max_length=200, default=""
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors = {
            name: "You must accept this to register."
            for name in ("accepted_terms", "accepted_privacy", "accepted_conduct")
            if not attrs[name]
        }
        if errors:
            raise serializers.ValidationError(errors)
        validate_new_password(attrs["password"], attrs["email"])
        return attrs


class GoogleRegistrationSerializer(StrictSerializer):
    """What a first-time Google user adds: consents and sign-up details, but no password."""

    accepted_terms = serializers.BooleanField()
    accepted_privacy = serializers.BooleanField()
    accepted_conduct = serializers.BooleanField()
    marketing_consent = serializers.BooleanField(required=False, default=False)
    also_mentor = serializers.BooleanField(
        required=False,
        default=False,
        help_text="I am also a mentor. Only records interest; an admin still approves.",
    )
    profile = SignupProfileSerializer()
    startup = SignupStartupSerializer()
    anonymous_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    referral = ReferralInputSerializer(required=False, default=dict)
    invitation_token = serializers.CharField(
        required=False, allow_blank=True, max_length=200, default=""
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors = {
            name: "You must accept this to register."
            for name in ("accepted_terms", "accepted_privacy", "accepted_conduct")
            if not attrs[name]
        }
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class GoogleSignInSerializer(StrictSerializer):
    id_token = serializers.CharField(max_length=4096, trim_whitespace=False)
    nonce = serializers.CharField(required=False, allow_blank=True, max_length=200, default="")
    registration = GoogleRegistrationSerializer(required=False)


class GoogleRegistrationRequiredSerializer(serializers.Serializer):
    code = serializers.CharField()
    detail = serializers.CharField()
    email = serializers.EmailField()
    name = serializers.CharField(allow_blank=True)


class TokenSerializer(StrictSerializer):
    token = serializers.CharField(max_length=200)


class LoginSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class InvitationPreviewSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.CharField()
    message = serializers.CharField(allow_blank=True)
    expires_at = serializers.DateTimeField()


class RegisteredSerializer(serializers.Serializer):
    detail = serializers.CharField()
    approved = serializers.BooleanField()


class ForgotPasswordSerializer(StrictSerializer):
    email = serializers.EmailField(max_length=254)


class ResetPasswordSerializer(StrictSerializer):
    token = serializers.CharField(max_length=200)
    password = serializers.CharField(max_length=128, trim_whitespace=False)

    def validate_password(self, value: str) -> str:
        return validate_new_password(value)


class AccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    status = serializers.CharField()


class AccessTokenSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    user = AccountSerializer()
    mfa_enrolment_required = serializers.BooleanField()


class MfaChallengeSerializer(serializers.Serializer):
    mfa_required = serializers.BooleanField()
    mfa_token = serializers.CharField()


class MfaVerifySerializer(StrictSerializer):
    mfa_token = serializers.CharField(max_length=500)
    code = serializers.CharField(max_length=32)


class CodeSerializer(StrictSerializer):
    code = serializers.CharField(max_length=32)


class MfaEnrolmentSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()


class MfaConfirmedSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()
    expires_in = serializers.IntegerField()
    recovery_codes = serializers.ListField(child=serializers.CharField())


class RecoveryCodesSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class MessageSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefreshTokenFamily
        fields = ["id", "user_agent", "created_at", "last_used_at", "expires_at"]
        read_only_fields = fields
