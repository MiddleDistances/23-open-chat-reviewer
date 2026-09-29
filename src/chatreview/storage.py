"""Explicit, resumable storage maintenance. Never deletes source evidence."""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Event
from typing import Annotated, Any

import typer
from dotenv import dotenv_values
from psycopg.errors import DeadlockDetected, LockNotAvailable, SerializationFailure

from chatreview.db import Session, database

app = typer.Typer(help="Audit, verify and compact archive storage; reporting is the default.")

# SQL and Python fingerprints intentionally share an unambiguous JSON array encoding.
FINGERPRINT_SQL = """'v1:' || encode(sha256(convert_to('v1' || chr(10) ||
    coalesce(string_agg(jsonb_build_array(m.event_id,m.episode_key)::text,chr(10)
    ORDER BY m.event_id) FILTER (WHERE m.event_id IS NOT NULL),''),'UTF8')),'hex')"""


def identity(connection: Session) -> dict[str, Any]:
    row = connection.execute("""SELECT current_database() AS database, current_schema() AS schema,
        (SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,
        current_setting('port') AS port, inet_server_addr()::text AS address,
        system_identifier::text AS system_identifier FROM pg_control_system()""").fetchone()
    assert row is not None
    result = dict(row)
    result["target"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def audit(connection: Session) -> dict[str, Any]:
    return {
        "identity": identity(connection),
        "database_bytes": connection.execute(
            "SELECT pg_database_size(current_database()) AS bytes"
        ).fetchone()["bytes"],
        "migrations": [
            dict(r)
            for r in connection.execute(
                "SELECT version,name,checksum FROM chatreview_schema_migrations ORDER BY version"
            ).fetchall()
        ],
        "tables": [
            dict(r)
            for r in connection.execute("""SELECT schemaname,relname,
            pg_total_relation_size(relid) AS total_bytes,pg_table_size(relid) AS data_bytes,
            pg_indexes_size(relid) AS index_bytes,n_live_tup,n_dead_tup,last_autovacuum,last_autoanalyze
            FROM pg_stat_user_tables WHERE schemaname=current_schema()
            ORDER BY pg_total_relation_size(relid) DESC""").fetchall()
        ],
    }


def require_target(connection: Session, target: str | None) -> None:
    if not target or identity(connection)["target"] != target:
        raise ValueError("Target identity mismatch; run storage audit with the same environment file")


def prepare_shared_sets(connection: Session) -> None:
    """Validate and register canonical fingerprints for predecessor sets without renumbering them."""
    connection.execute(f"""CREATE TEMP TABLE storage_existing ON COMMIT DROP AS
        SELECT s.id,s.fingerprint AS stored_fingerprint,s.member_count,
               count(m.event_id) AS actual,{FINGERPRINT_SQL} AS fingerprint
        FROM timesheet_evidence_sets s LEFT JOIN timesheet_evidence_members m ON m.evidence_set_id=s.id
        GROUP BY s.id""")
    if connection.execute("SELECT 1 FROM storage_existing WHERE member_count<>actual LIMIT 1").fetchone():
        raise ValueError("Existing shared evidence member count mismatch")
    if connection.execute("""SELECT 1 FROM storage_existing
        WHERE stored_fingerprint LIKE 'v1:%' AND stored_fingerprint<>fingerprint LIMIT 1""").fetchone():
        raise ValueError("Existing canonical evidence fingerprint mismatch")
    # Identical sets may predate canonical fingerprints. Keep every ID, register one representative.
    connection.execute("""UPDATE timesheet_evidence_sets s SET fingerprint=x.fingerprint
        FROM (SELECT fingerprint,min(id) AS id FROM storage_existing GROUP BY fingerprint) x
        WHERE s.id=x.id AND s.fingerprint<>x.fingerprint
        AND NOT EXISTS (SELECT 1 FROM timesheet_evidence_sets existing
                        WHERE existing.fingerprint=x.fingerprint)""")
    connection.execute("LOCK TABLE work_interval_evidence IN SHARE MODE")
    if connection.execute("""SELECT 1 FROM work_intervals w
        JOIN timesheet_evidence_sets s ON s.id=w.evidence_set_id
        WHERE w.evidence_count<>s.member_count LIMIT 1""").fetchone():
        raise ValueError("Existing shared interval count mismatch")
    connection.execute("""INSERT INTO storage_interval_verification(interval_id,evidence_set_id,member_count)
        SELECT w.id,w.evidence_set_id,w.evidence_count FROM work_intervals w
        WHERE w.evidence_set_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM work_interval_evidence old WHERE old.interval_id=w.id)
        ON CONFLICT (interval_id) DO NOTHING""")
    connection.commit()


def backfill_batch(
    connection: Session, batch_size: int = 200, *, after_id: int = 0, end_id: int = 9223372036854775807
) -> dict[str, int]:
    """Certify full equality before linking; commit links and proof in the same transaction."""
    connection.execute("LOCK TABLE work_interval_evidence IN SHARE MODE")
    connection.execute(
        """CREATE TEMP TABLE storage_targets ON COMMIT DROP AS
        SELECT w.id,w.evidence_set_id,w.evidence_count FROM work_intervals w
        LEFT JOIN storage_interval_verification proof ON proof.interval_id=w.id
        WHERE w.id>? AND w.id<=? AND proof.interval_id IS NULL ORDER BY w.id LIMIT ? FOR UPDATE OF w""",
        (after_id, end_id, batch_size),
    )
    connection.execute("ANALYZE storage_targets")
    row = connection.execute("SELECT count(*) AS n,max(id) AS last FROM storage_targets").fetchone()
    if not row["n"]:
        connection.rollback()
        return {"intervals": 0, "last_interval_id": after_id}
    connection.execute("""CREATE TEMP TABLE storage_members ON COMMIT DROP AS
        SELECT target.id AS interval_id,e.event_id,e.episode_key FROM storage_targets target
        CROSS JOIN LATERAL (
            SELECT event_id,episode_key FROM work_interval_evidence
            WHERE interval_id=target.id OFFSET 0
        ) e""")
    connection.execute("CREATE INDEX ON storage_members(interval_id,event_id)")
    connection.execute("ANALYZE storage_members")
    # OFFSET 0 above retains parameterized lookups despite skewed legacy statistics.
    connection.execute(f"""CREATE TEMP TABLE storage_sets ON COMMIT DROP AS
        SELECT t.id,t.evidence_set_id,t.evidence_count,count(m.event_id) AS actual,
               {FINGERPRINT_SQL} AS fingerprint
        FROM storage_targets t LEFT JOIN storage_members m ON m.interval_id=t.id
        GROUP BY t.id,t.evidence_set_id,t.evidence_count""")
    if connection.execute("""SELECT 1 FROM storage_sets
        WHERE evidence_set_id IS NULL AND evidence_count<>actual LIMIT 1""").fetchone():
        raise ValueError("Legacy interval evidence count mismatch")
    connection.execute("""CREATE TEMP TABLE storage_new_sets ON COMMIT DROP AS
        WITH inserted AS (
            INSERT INTO timesheet_evidence_sets(fingerprint,member_count)
            SELECT DISTINCT fingerprint,actual FROM storage_sets WHERE evidence_set_id IS NULL
            ORDER BY fingerprint
            ON CONFLICT (fingerprint) DO NOTHING RETURNING id,fingerprint
        ) SELECT * FROM inserted""")
    connection.execute("""INSERT INTO timesheet_evidence_members(evidence_set_id,event_id,episode_key)
        SELECT DISTINCT n.id,m.event_id,m.episode_key FROM storage_new_sets n
        JOIN storage_sets s ON s.fingerprint=n.fingerprint
        JOIN storage_members m ON m.interval_id=s.id""")
    connection.execute("""ALTER TABLE storage_sets ADD COLUMN target_set_id bigint""")
    connection.execute("""UPDATE storage_sets s SET target_set_id=coalesce(s.evidence_set_id,t.id)
        FROM timesheet_evidence_sets t WHERE t.fingerprint=s.fingerprint""")
    connection.execute("""UPDATE storage_sets SET target_set_id=evidence_set_id
        WHERE evidence_set_id IS NOT NULL""")
    connection.execute("ANALYZE storage_sets")
    connection.execute("""CREATE TEMP TABLE storage_expected ON COMMIT DROP AS
        SELECT m.* FROM (SELECT DISTINCT target_set_id FROM storage_sets) target
        CROSS JOIN LATERAL (
            SELECT evidence_set_id,event_id,episode_key FROM timesheet_evidence_members
            WHERE evidence_set_id=target.target_set_id OFFSET 0
        ) m""")
    connection.execute("ANALYZE storage_expected")
    connection.execute("""CREATE TEMP TABLE storage_set_counts ON COMMIT DROP AS
        SELECT target.target_set_id,count(m.event_id) AS actual
        FROM (SELECT DISTINCT target_set_id FROM storage_sets) target
        LEFT JOIN storage_expected m ON m.evidence_set_id=target.target_set_id
        GROUP BY target.target_set_id""")
    # Both cardinality and null-safe equality are required; hashes alone are not proof.
    if connection.execute("""SELECT 1 FROM storage_sets s
        LEFT JOIN timesheet_evidence_sets t ON t.id=s.target_set_id
        LEFT JOIN storage_set_counts counts ON counts.target_set_id=s.target_set_id
        WHERE t.id IS NULL OR t.member_count<>s.evidence_count
        OR counts.actual<>s.evidence_count LIMIT 1""").fetchone():
        raise ValueError("Shared evidence cardinality mismatch")
    if connection.execute("""SELECT count(*) AS mismatches FROM storage_members old
        JOIN storage_sets s ON s.id=old.interval_id
        LEFT JOIN storage_expected m
          ON m.evidence_set_id=s.target_set_id AND m.event_id=old.event_id
        WHERE m.event_id IS NULL OR m.episode_key IS DISTINCT FROM old.episode_key""").fetchone()[
        "mismatches"
    ]:
        raise ValueError("Legacy/shared evidence membership mismatch")
    if connection.execute("""SELECT 1 FROM storage_sets
        WHERE actual>0 AND actual<>evidence_count LIMIT 1""").fetchone():
        raise ValueError("Partial legacy/shared evidence membership")
    connection.execute("""UPDATE work_intervals w SET evidence_set_id=s.target_set_id
        FROM storage_sets s WHERE w.id=s.id AND w.evidence_set_id IS NULL""")
    connection.execute("""INSERT INTO storage_interval_verification(interval_id,evidence_set_id,member_count)
        SELECT id,target_set_id,evidence_count FROM storage_sets""")
    connection.execute(
        """INSERT INTO storage_maintenance_progress(
            operation,last_interval_id,intervals_verified)
        VALUES ('evidence',?,?) ON CONFLICT (operation) DO UPDATE
        SET last_interval_id=greatest(
            storage_maintenance_progress.last_interval_id,EXCLUDED.last_interval_id),
            intervals_verified=storage_maintenance_progress.intervals_verified+EXCLUDED.intervals_verified,
            updated_at=clock_timestamp()""",
        (row["last"], row["n"]),
    )
    connection.commit()
    return {"intervals": int(row["n"]), "last_interval_id": int(row["last"])}


def backfill_range(
    url: str, start: int, end: int, batch_size: int, stopped: Event | None = None
) -> dict[str, int]:
    """Disjoint ranges share immutable sets; certificates are the resume authority."""
    total = 0
    with database(url) as connection:
        cursor = start
        while True:
            if stopped is not None and stopped.is_set():
                return {"range_start": start, "range_end": end, "intervals": total}
            for attempt in range(4):
                try:
                    result = backfill_batch(connection, batch_size, after_id=cursor, end_id=end)
                    break
                except (DeadlockDetected, LockNotAvailable, SerializationFailure):
                    connection.rollback()
                    if attempt == 3:
                        raise
                    time.sleep(0.25 * 2**attempt)
            if not result["intervals"]:
                return {"range_start": start, "range_end": end, "intervals": total}
            total += result["intervals"]
            cursor = result["last_interval_id"]


def verify(connection: Session) -> dict[str, int]:
    missing = connection.execute("""SELECT count(*) AS n FROM work_intervals w
        LEFT JOIN storage_interval_verification p ON p.interval_id=w.id
        WHERE p.interval_id IS NULL OR p.evidence_set_id IS DISTINCT FROM w.evidence_set_id
        OR p.member_count<>w.evidence_count""").fetchone()["n"]
    corrupt = connection.execute(f"""SELECT count(*) AS n FROM (
        SELECT s.id FROM timesheet_evidence_sets s
        LEFT JOIN timesheet_evidence_members m ON m.evidence_set_id=s.id
        GROUP BY s.id HAVING s.member_count<>count(m.event_id)
        OR (s.fingerprint LIKE 'v1:%' AND s.fingerprint<>({FINGERPRINT_SQL}))) x""").fetchone()["n"]
    return {"uncertified_intervals": int(missing), "invalid_sets": int(corrupt)}


def reclaim(connection: Session) -> dict[str, int]:
    # Lock every mutable input to the proof before checking and releasing old storage.
    connection.execute("SET LOCAL lock_timeout='10s'")
    connection.execute("""LOCK TABLE work_intervals,timesheet_evidence_sets,
        timesheet_evidence_members,storage_interval_verification IN SHARE ROW EXCLUSIVE MODE""")
    connection.execute("LOCK TABLE work_interval_evidence IN ACCESS EXCLUSIVE MODE")
    result = verify(connection)
    if any(result.values()):
        raise ValueError(f"Reclamation requires complete verification: {result}")
    before = connection.execute(
        "SELECT pg_total_relation_size('work_interval_evidence') AS bytes"
    ).fetchone()["bytes"]
    connection.execute("TRUNCATE TABLE work_interval_evidence")
    # The migration-defined guard is activated atomically with reclamation.
    connection.execute("""INSERT INTO schema_meta(key,value)
        VALUES ('timesheet_legacy_evidence_retired','1')
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""")
    connection.commit()
    after = connection.execute("SELECT pg_total_relation_size('work_interval_evidence') AS bytes").fetchone()[
        "bytes"
    ]
    return {"before_bytes": before, "after_bytes": after, "reclaimed_bytes": before - after}


@app.command("run")
def storage_command(
    operation: Annotated[str, typer.Argument(help="audit, backfill, verify, or reclaim")] = "audit",
    env_file: Annotated[Path | None, typer.Option()] = None,
    apply: Annotated[bool, typer.Option("--apply")] = False,
    target: Annotated[str | None, typer.Option()] = None,
    batch_size: Annotated[int, typer.Option(min=1, max=2000)] = 200,
    max_batches: Annotated[int | None, typer.Option(min=1)] = None,
    workers: Annotated[int, typer.Option(min=1, max=4)] = 1,
) -> None:
    """Honor the explicit environment without sourcing executable shell or printing credentials."""
    if operation not in {"audit", "backfill", "verify", "reclaim"}:
        raise typer.BadParameter("Unknown storage operation")
    selected = env_file or (
        Path(os.environ["CHATREVIEW_ENV_FILE"]) if os.environ.get("CHATREVIEW_ENV_FILE") else None
    )
    if selected is not None:
        if not selected.is_file():
            raise typer.BadParameter("Selected environment file does not exist")
        url = dotenv_values(selected, interpolate=False).get("CHATREVIEW_DATABASE_URL")
        if not url:
            raise typer.BadParameter("Selected environment file must define CHATREVIEW_DATABASE_URL")
    else:
        url = os.environ.get("CHATREVIEW_DATABASE_URL")
    if not url:
        raise typer.BadParameter("Supply --env-file or CHATREVIEW_DATABASE_URL")
    if workers > 1 and max_batches is not None:
        raise typer.BadParameter("--max-batches requires --workers=1")
    mutating = apply and operation in {"backfill", "reclaim"}
    with database(url, read_only=not mutating) as connection:
        typer.echo(json.dumps({"identity": identity(connection)}, default=str), err=True)
        if mutating:
            require_target(connection, target)
        if not mutating:
            report = verify(connection) if operation == "verify" else audit(connection)
            typer.echo(json.dumps(report, default=str))
            return
        with connection.try_advisory_lock("storage-maintenance") as acquired:
            if not acquired:
                raise ValueError("Another storage maintenance process is active")
            if operation == "reclaim":
                typer.echo(json.dumps(reclaim(connection)))
            else:
                prepare_shared_sets(connection)
                if workers > 1:
                    maximum = connection.execute(
                        "SELECT coalesce(max(id),0) AS id FROM work_intervals"
                    ).fetchone()["id"]
                    connection.commit()
                    stopped = Event()
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        futures = [
                            executor.submit(backfill_range, url, start, start + 10000, batch_size, stopped)
                            for start in range(0, maximum, 10000)
                        ]
                        try:
                            for future in as_completed(futures):
                                typer.echo(json.dumps(future.result()))
                        except BaseException:
                            stopped.set()
                            for future in futures:
                                future.cancel()
                            raise
                    return
                after_id = 0
                batches = 0
                while True:
                    result = backfill_batch(connection, batch_size, after_id=after_id)
                    typer.echo(json.dumps(result))
                    if not result["intervals"]:
                        break
                    after_id = result["last_interval_id"]
                    batches += 1
                    if max_batches and batches >= max_batches:
                        break
