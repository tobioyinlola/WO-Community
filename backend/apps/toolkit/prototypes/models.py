from django.db import models

from apps.core.models import BaseModel


class PrototypeTemplate(BaseModel):
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    spec = models.JSONField(default=dict)
    position = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]


class Prototype(BaseModel):
    venture = models.ForeignKey(
        "tk_ventures.Venture", on_delete=models.CASCADE, related_name="prototypes"
    )
    title = models.CharField(max_length=120)
    template_slug = models.CharField(max_length=40, blank=True)
    spec = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=["venture", "-updated_at"], name="tk_proto_venture_idx")]


class PrototypeVersion(BaseModel):
    prototype = models.ForeignKey(Prototype, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    spec = models.JSONField(default=dict)
    label = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["prototype", "version"], name="tk_protoversion_unique")
        ]
        ordering = ["-version"]
