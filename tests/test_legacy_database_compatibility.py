from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from chatreview.db import DatabaseError, close_pools, database, doctor, migrate

LEGACY_V1_CHECKSUM = "f7abb72c1878dc702ce80f2febef40cf897cbff08bb938f0b5e8e8c76575e740"
LEGACY_V15_CHECKSUM = "e47f76844b3eb261f42f5a89c0d038776caad8ee231e449c68b5aab7f7f93f2d"
LEGACY_V16_CHECKSUM = "872530752bd21d757169d25daab04f5d846bcbd334bed9372366c78884db38e6"


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
        with pytest.raises(DatabaseError, match="migration 1 differs"):
            doctor(database_url)
    finally:
        close_pools()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_migrate_adds_public_token_tables_after_private_versions_15_and_16() -> None:
    schema = f"legacy_{uuid4().hex}"
    base_url = os.environ.get(
        "CHATREVIEW_TEST_DATABASE_URL", "postgresql:///chatreview?port=6543"
    )
    parameters = conninfo_to_dict(base_url)
    parameters["options"] = f"-c search_path={schema},public"
    database_url = make_conninfo(**parameters)

    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    try:
        migrate(database_url)
        with psycopg.connect(database_url) as connection:
            connection.execute("ALTER TABLE activities RENAME TO rd_activities")
            connection.execute(
                "CREATE VIEW activities AS SELECT id, code, title, classification, "
                "reporting_period_start, reporting_period_end, description, "
                "uncertainty_or_hypothesis, created_at, updated_at FROM rd_activities"
            )
            connection.execute(
                "ALTER TABLE resume_surfaces ADD COLUMN human_summary text NOT NULL DEFAULT ''"
            )
            connection.execute(
                "CREATE TABLE semantic_session_state ("
                "run_id bigint NOT NULL REFERENCES semantic_runs(id) ON DELETE CASCADE, "
                "session_id bigint NOT NULL REFERENCES sessions(id) ON DELETE CASCADE, "
                "input_fingerprint text NOT NULL, indexed_at timestamptz NOT NULL "
                "DEFAULT clock_timestamp(), PRIMARY KEY (run_id, session_id))"
            )
            connection.execute(
                "DROP TABLE token_cost_rows, token_cost_snapshots, token_cost_settings, "
                "token_price_books, event_token_usage"
            )
            connection.execute("DELETE FROM chatreview_schema_migrations WHERE version IN (20, 21)")
            connection.execute(
                "UPDATE chatreview_schema_migrations SET checksum=%s WHERE version=1",
                (LEGACY_V1_CHECKSUM,),
            )
            connection.execute(
                "UPDATE chatreview_schema_migrations SET name=%s, checksum=%s WHERE version=15",
                ("0015_resume_human_summary.sql", LEGACY_V15_CHECKSUM),
            )
            connection.execute(
                "UPDATE chatreview_schema_migrations SET name=%s, checksum=%s WHERE version=16",
                ("0016_semantic_incremental_state.sql", LEGACY_V16_CHECKSUM),
            )
            connection.commit()

        assert doctor(database_url).migration_count == 11
        assert migrate(database_url) == [
            "0020_token_usage_legacy_compatibility.sql",
            "0021_token_costs_legacy_compatibility.sql",
        ]
        assert migrate(database_url) == []
        with psycopg.connect(database_url) as connection:
            for table in ("event_token_usage", "token_price_books", "token_cost_rows"):
                relation = connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()
                assert relation is not None and relation[0] is not None
            connection.execute("ALTER TABLE resume_surfaces DROP COLUMN human_summary")
            connection.commit()
        with pytest.raises(DatabaseError, match="migration 15 differs"):
            doctor(database_url)
    finally:
        close_pools()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
