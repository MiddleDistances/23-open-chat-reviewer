from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from chatreview.db import DatabaseError, close_pools, database, migrate

LEGACY_V1_CHECKSUM = "f7abb72c1878dc702ce80f2febef40cf897cbff08bb938f0b5e8e8c76575e740"


def test_migrate_accepts_exact_legacy_archive_and_adds_activity_view() -> None:
    """The open-source GUI can read the populated predecessor database safely."""

    schema = f"legacy_{uuid4().hex}"
    base_url = os.environ.get(
        "CHATREVIEW_TEST_DATABASE_URL", "postgresql:///chatreview?port=6543"
    )
    parameters = conninfo_to_dict(base_url)
    parameters["options"] = f"-c search_path={schema},public"
    database_url = make_conninfo(**parameters)
    migration_one = (
        Path(__file__).parents[1]
        / "src/chatreview/migrations/0001_postgresql_archive.sql"
    ).read_text(encoding="utf-8")

    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    try:
        with psycopg.connect(database_url) as connection:
            connection.execute(migration_one)
            connection.execute("ALTER TABLE activities RENAME TO rd_activities")
            connection.execute(
                """
                CREATE TABLE chatreview_schema_migrations (
                    version integer PRIMARY KEY,
                    name text NOT NULL UNIQUE,
                    checksum text NOT NULL,
                    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
            connection.execute(
                """
                INSERT INTO chatreview_schema_migrations(version, name, checksum)
                VALUES (1, '0001_postgresql_archive.sql', %s)
                """,
                (LEGACY_V1_CHECKSUM,),
            )
            connection.commit()

        applied = migrate(database_url)
        applied_again = migrate(database_url)

        assert "0014_legacy_activity_compatibility.sql" in applied
        assert applied_again == []
        with database(database_url, read_only=True) as connection:
            relation = connection.execute(
                "SELECT relkind FROM pg_class WHERE oid=to_regclass('activities')"
            ).fetchone()
            assert relation is not None
            assert relation["relkind"] == "v"

        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE chatreview_schema_migrations SET checksum='unknown' WHERE version=1"
            )
            connection.commit()
        with pytest.raises(DatabaseError, match="migration 1 differs"):
            migrate(database_url)
    finally:
        close_pools()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
