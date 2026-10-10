from django.db import migrations

from apps.audit.partitions import ensure_month_partitions

CREATE_TABLE = """
CREATE SEQUENCE audit_auditlog_seq;

CREATE TABLE audit_auditlog (
    id uuid NOT NULL,
    created_at timestamptz NOT NULL,
    seq bigint NOT NULL,
    actor_id uuid,
    actor_roles jsonb NOT NULL DEFAULT '[]',
    action varchar(100) NOT NULL,
    target_type varchar(100) NOT NULL DEFAULT '',
    target_id varchar(64) NOT NULL DEFAULT '',
    before jsonb,
    after jsonb,
    reason text NOT NULL DEFAULT '',
    ip_hash varchar(64) NOT NULL DEFAULT '',
    user_agent_hash varchar(64) NOT NULL DEFAULT '',
    prev_hash varchar(64) NOT NULL DEFAULT '',
    hash varchar(64) NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Last resort: rows outside any prepared month land here instead of failing the request.
CREATE TABLE audit_auditlog_default PARTITION OF audit_auditlog DEFAULT;

CREATE INDEX audit_auditlog_seq_idx ON audit_auditlog (created_at, seq);
CREATE INDEX audit_auditlog_actor_idx ON audit_auditlog (actor_id, created_at);
CREATE INDEX audit_auditlog_target_idx ON audit_auditlog (target_type, target_id);

CREATE FUNCTION audit_auditlog_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog is append only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_auditlog_no_change
    BEFORE UPDATE OR DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_auditlog_immutable();
"""

DROP_TABLE = """
DROP TABLE audit_auditlog;
DROP FUNCTION audit_auditlog_immutable();
DROP SEQUENCE audit_auditlog_seq;
"""


def create_initial_partitions(apps, schema_editor):
    from django.utils import timezone

    ensure_month_partitions(timezone.now().date(), months_ahead=3)


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []

    operations = [
        migrations.RunSQL(CREATE_TABLE, DROP_TABLE),
        migrations.RunPython(create_initial_partitions, migrations.RunPython.noop),
        migrations.CreateModel(
            name="AuditLog",
            fields=[],
            options={"db_table": "audit_auditlog", "managed": False, "ordering": ["seq"]},
        ),
    ]
