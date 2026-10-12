from django.db import models

from apps.core.ids import uuid7


class AuditLog(models.Model):
    """Append only record of sensitive actions.

    The table is range partitioned by month and created with raw SQL (see the
    initial migration), so Django does not manage it. Database triggers reject
    UPDATE and DELETE; production also revokes those grants from the app role.
    Actor and target are stored as plain ids, not foreign keys, so erasing a
    person never touches the audit trail.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_at = models.DateTimeField()
    seq = models.BigIntegerField()
    actor_id = models.UUIDField(null=True)
    actor_roles = models.JSONField(default=list)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    reason = models.TextField(blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64)

    class Meta:
        managed = False
        db_table = "audit_auditlog"
        ordering = ["seq"]

    def __str__(self) -> str:
        return f"{self.seq} {self.action}"
