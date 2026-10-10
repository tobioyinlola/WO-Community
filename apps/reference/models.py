from django.db import models
from django.db.models.functions import Lower

from apps.core.models import BaseModel


class ReferenceItem(BaseModel):
    """A managed list entry. Deactivated entries stay for old records but cannot be picked."""

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="%(app_label)s_%(class)s_name_ci_unique")
        ]

    def __str__(self) -> str:
        return self.name


class Sector(ReferenceItem):
    pass


class Stage(ReferenceItem):
    pass


class Skill(ReferenceItem):
    pass
