"""Make audit_log append-only at the database level in production (SCHEMA.md §2.13).

Set AUDIT_LOG_REVOKE_ROLE to the application's DB role (e.g. the Neon/Render role name).
No-op when unset (local dev and tests need TRUNCATE/DELETE for fixtures).
"""
import os
import re

from django.db import migrations


def revoke(apps, schema_editor):
    role = os.environ.get("AUDIT_LOG_REVOKE_ROLE", "").strip()
    if not role:
        return
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\-]*", role):
        raise ValueError("Invalid AUDIT_LOG_REVOKE_ROLE")
    schema_editor.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM "{role}"')
    schema_editor.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON dispute_events FROM "{role}"')
    schema_editor.execute(f'REVOKE UPDATE, DELETE, TRUNCATE ON fx_rates FROM "{role}"')


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_initial"),
        ("disputes", "0001_initial"),
        ("masterdata", "0001_initial"),
    ]

    operations = [migrations.RunPython(revoke, migrations.RunPython.noop)]
