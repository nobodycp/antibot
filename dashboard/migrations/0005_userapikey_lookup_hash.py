import hashlib

from django.db import migrations, models


def _drop_orphan_lookup_hash_indexes(apps, schema_editor):
    """Recover from a failed partial apply on PostgreSQL (duplicate _like index)."""
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    qn = schema_editor.quote_name
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE tablename = %s
              AND indexname LIKE %s
            """,
            ["dashboard_userapikey", "%api_key_lookup_hash%"],
        )
        for (idxname,) in cursor.fetchall():
            cursor.execute("DROP INDEX IF EXISTS " + qn(idxname))


def _add_lookup_hash_column_if_missing(apps, schema_editor):
    table = "dashboard_userapikey"
    column = "api_key_lookup_hash"
    conn = schema_editor.connection
    with conn.cursor() as cursor:
        if conn.vendor == "sqlite":
            cursor.execute(f"PRAGMA table_info({table})")
            if any(row[1] == column for row in cursor.fetchall()):
                return
            cursor.execute(
                f'ALTER TABLE {table} ADD COLUMN {column} varchar(64) NULL'
            )
        elif conn.vendor == "postgresql":
            cursor.execute(
                """
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s
                  AND column_name = %s
                """,
                [table, column],
            )
            if cursor.fetchone()[0]:
                return
            cursor.execute(
                "ALTER TABLE dashboard_userapikey "
                "ADD COLUMN api_key_lookup_hash varchar(64) NULL"
            )


def _backfill_api_key_lookup_hash(apps, schema_editor):
    UserAPIKey = apps.get_model("dashboard", "UserAPIKey")
    for row in UserAPIKey.objects.all().iterator():
        if row.api_key:
            row.api_key_lookup_hash = hashlib.sha256(
                row.api_key.encode("utf-8")
            ).hexdigest()
            row.save(update_fields=["api_key_lookup_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0004_user_api_key"),
    ]

    operations = [
        migrations.RunPython(
            _drop_orphan_lookup_hash_indexes,
            migrations.RunPython.noop,
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="userapikey",
                    name="api_key_lookup_hash",
                    field=models.CharField(
                        editable=False,
                        max_length=64,
                        null=True,
                        unique=False,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _add_lookup_hash_column_if_missing,
                    migrations.RunPython.noop,
                ),
            ],
        ),
        migrations.RunPython(_backfill_api_key_lookup_hash, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userapikey",
            name="api_key_lookup_hash",
            field=models.CharField(
                db_index=True,
                default="",
                editable=False,
                max_length=64,
                unique=True,
            ),
        ),
    ]
