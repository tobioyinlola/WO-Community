from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel

DECK_STATUSES = ("draft", "ready")


class DeckTemplate(BaseModel):
    """A starting structure for a deck. Admin managed; ``slides`` is the seed spec."""

    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    slides = models.JSONField(default=list)
    position = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]


class Deck(BaseModel):
    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="decks"
    )
    title = models.CharField(max_length=120)
    template_slug = models.CharField(max_length=40, blank=True)
    content = models.JSONField(default=dict)  # {"slides": [...], "theme": {...}}
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=8, default="draft")
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=DECK_STATUSES), name="tk_deck_status_valid"
            )
        ]
        indexes = [models.Index(fields=["venture", "-updated_at"], name="tk_deck_venture_idx")]


class DeckVersion(BaseModel):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    content = models.JSONField(default=dict)
    label = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["deck", "version"], name="tk_deckversion_unique")
        ]
        ordering = ["-version"]


class DeckAsset(BaseModel):
    """An image the member added to a deck, re-encoded and kept privately."""

    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="assets")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="toolkit_deck_assets"
    )
    storage_key = models.CharField(max_length=200, unique=True)
    content_type = models.CharField(max_length=60)
    size = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    filename = models.CharField(max_length=120, blank=True)
