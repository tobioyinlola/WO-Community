from django.db import models

from apps.core.models import BaseModel


class OnboardingState(BaseModel):
    """Remembers that a member finished the checklist, so the event is recorded once."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="onboarding_state"
    )
    completed_at = models.DateTimeField(null=True, blank=True)
