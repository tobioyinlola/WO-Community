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
        return self.status in (UserStatus.ACTIVE, UserStatus.PENDING)

    def role_names(self) -> frozenset[str]:
        cached = getattr(self, "_role_names", None)
        if cached is None:
            cached = frozenset(self.user_roles.values_list("role", flat=True))
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
