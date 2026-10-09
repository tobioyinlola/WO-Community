from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import BaseModel
from apps.core.rbac import Role


class UserStatus(models.TextChoices):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REMOVED = "removed"
    REJECTED = "rejected"


# Accounts in these states cannot authenticate, refresh or receive account emails.
BLOCKED_STATUSES = (UserStatus.SUSPENDED, UserStatus.REMOVED, UserStatus.REJECTED)


class ApprovalSource(models.TextChoices):
    ADMIN = "admin"
    INVITATION = "invitation"


class UserManager(BaseUserManager["User"]):
    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def get_by_natural_key(self, username: str | None) -> "User":
        return self.get(email__iexact=username or "")


class User(BaseModel, AbstractBaseUser):
    email = models.EmailField(max_length=254)
    status = models.CharField(max_length=12, choices=UserStatus.choices, default=UserStatus.PENDING)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    approval_source = models.CharField(max_length=12, choices=ApprovalSource.choices, blank=True)
    # Why the account is in its current state (rejection, suspension, removal).
    status_reason = models.TextField(blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    locale = models.CharField(max_length=10, default="en")
    timezone = models.CharField(max_length=64, default="UTC")
    # Bumped on role change or suspension so already issued access tokens stop working.
    token_version = models.PositiveIntegerField(default=1)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="user_email_ci_unique")]
        indexes = [
            models.Index(fields=["status", "created_at"], name="user_status_created_idx"),
            models.Index(
                fields=["created_at"],
                name="user_pending_idx",
                condition=models.Q(status="pending"),
            ),
        ]

    def __str__(self) -> str:
        return str(self.pk)

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self.status not in BLOCKED_STATUSES

    def role_names(self) -> frozenset[str]:
        cached = getattr(self, "_role_names", None)
        if cached is None:
            # .all() so a prefetch_related("user_roles") in a list view is used.
            cached = frozenset(role.role for role in self.user_roles.all())
            self._role_names = cached
        return cached

    def bump_token_version(self) -> None:
        self.token_version = models.F("token_version") + 1
        self.save(update_fields=["token_version", "updated_at"])
        self.refresh_from_db(fields=["token_version"])
        self.__dict__.pop("_role_names", None)

    def mark_login(self) -> None:
        self.last_login = timezone.now()
        self.save(update_fields=["last_login"])


class UserRole(BaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.CharField(max_length=20, choices=[(r.value, r.value) for r in Role])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="userrole_unique")]


class ConsentDocument(models.TextChoices):
    TERMS = "terms"
    PRIVACY = "privacy"
    CONDUCT = "conduct"
    MARKETING = "marketing"


class ConsentRecord(BaseModel):
    """One versioned grant or withdrawal of consent, kept as history."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    document = models.CharField(max_length=12, choices=ConsentDocument.choices)
    version = models.CharField(max_length=20)
    granted = models.BooleanField(default=True)
    ip_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "document", "version"], name="consent_lookup_idx")]

    def __str__(self) -> str:
        return f"{self.document} v{self.version} granted={self.granted}"


class EmailTokenPurpose(models.TextChoices):
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"  # noqa: S105  # nosec B105


class EmailToken(BaseModel):
    """Single use token sent by email. Only its hash is stored."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_tokens")
    purpose = models.CharField(max_length=20, choices=EmailTokenPurpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.purpose} for {self.user_id}"


class RefreshTokenFamily(BaseModel):
    """A login session. The refresh token rotates on every use.

    Presenting a token that is not the current one means it was stolen or
    replayed, so the whole family is revoked.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_families")
    current_hash = models.CharField(max_length=64)
    user_agent = models.CharField(max_length=255, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    absolute_expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=30, blank=True)
    # When this session last passed an MFA check; carried into every access token.
    mfa_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "revoked_at"], name="refresh_user_revoked_idx")]

    def __str__(self) -> str:
        return f"session {self.pk}"


class MfaDevice(BaseModel):
    """A user's TOTP authenticator. The secret is encrypted at rest."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="mfa_device")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Highest time step already accepted, so a code cannot be used twice.
    last_used_step = models.BigIntegerField(default=0)

    def __str__(self) -> str:
        return f"mfa device of {self.user_id}"


class RecoveryCode(BaseModel):
    """One time backup code for a lost authenticator. Only its hash is stored."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"recovery code of {self.user_id}"
