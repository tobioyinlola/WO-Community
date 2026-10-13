from django.db import migrations

ADD = """
ALTER TABLE audit_auditlog
    ADD COLUMN outcome varchar(10) NOT NULL DEFAULT 'success',
    ADD COLUMN request_id varchar(64) NOT NULL DEFAULT '',
    ADD COLUMN target_label varchar(200) NOT NULL DEFAULT '';
CREATE INDEX audit_auditlog_action_idx ON audit_auditlog (action, created_at);
"""

DROP = """
DROP INDEX audit_auditlog_action_idx;
ALTER TABLE audit_auditlog DROP COLUMN outcome, DROP COLUMN request_id, DROP COLUMN target_label;
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    # Informational columns: not part of the hash chain, so every earlier row still verifies.
    operations = [migrations.RunSQL(ADD, DROP)]
