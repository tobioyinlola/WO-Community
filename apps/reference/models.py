from django.db import models

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

    def __str__(self) -> str:
        return self.name


class Sector(ReferenceItem):
    pass


class Stage(ReferenceItem):
    pass


class Skill(ReferenceItem):
    pass
