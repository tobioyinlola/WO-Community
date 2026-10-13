"""Creates the first super admin on a new deployment, where nobody can invite or approve yet.

    python manage.py create_super_admin --email you@example.com

The password is asked for twice. For a non interactive run, put it in ADMIN_PASSWORD. The account
is active at once; it still has to set up two step sign in the first time it signs in.
"""

import os
from getpass import getpass
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User, UserRole, UserStatus


class Command(BaseCommand):
    help = "Create a super admin account (for the first administrator of a new deployment)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        email = options["email"].strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise CommandError("That is not an email address.")
        if User.objects.filter(email=email).exists():
            raise CommandError(f"An account for {email} already exists.")
        password = os.environ.get("ADMIN_PASSWORD") or self._ask()
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        now = timezone.now()
        with transaction.atomic():
            user = User.objects.create_user(email, password)
            user.status = UserStatus.ACTIVE
            user.email_verified_at = now
            user.approved_at = now
            user.save()
            UserRole.objects.create(user=user, role=Role.SUPER_ADMIN.value)
        self.stdout.write(self.style.SUCCESS(f"Created the super admin {email}."))

    @staticmethod
    def _ask() -> str:
        first = getpass("Password: ")
        if first != getpass("Password (again): "):
            raise CommandError("The passwords do not match.")
        return first
