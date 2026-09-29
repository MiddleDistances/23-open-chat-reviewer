from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import psycopg
import pytest

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.shared_evidence import evidence_fingerprint, persist_evidence
from chatreview.storage import (
    FINGERPRINT_SQL,
    backfill_batch,
    identity,
    prepare_shared_sets,
    reclaim,
    require_target,
    verify,
)
from chatreview.timesheets import build_timesheet


@pytest.fixture()
def archive(corpus):
    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)]).run()
    with database(settings.database_url) as c:
        build_timesheet(c, cutoff=datetime(2026, 7, 20, tzinfo=UTC))
    return settings.database_url


def test_fingerprint_matches_sql_unicode_null_and_order(archive):
    with database(archive) as c:
        rows = c.execute("SELECT id AS event_id FROM events ORDER BY id LIMIT 2").fetchall()
        members = [(rows[0]["event_id"], None), (rows[1]["event_id"], 'é"\\\n日本')]
        c.execute("CREATE TEMP TABLE fingerprint_members(event_id bigint,episode_key text)")
        c.executemany("INSERT INTO fingerprint_members VALUES (?,?)", members[::-1])
        sql = c.execute(f"SELECT {FINGERPRINT_SQL} AS fingerprint FROM fingerprint_members m").fetchone()
        assert sql["fingerprint"] == evidence_fingerprint(members)
        assert persist_evidence(c, []) == persist_evidence(c, [])


def test_new_snapshot_reuses_membership_and_retains_cutoff(archive):
    with database(archive) as c:
        before = c.execute("SELECT count(*) AS n FROM timesheet_evidence_members").fetchone()["n"]
        later = build_timesheet(c, cutoff=datetime(2026, 7, 21, tzinfo=UTC))
        assert later.cutoff == datetime(2026, 7, 21, tzinfo=UTC)
        assert c.execute("SELECT count(*) AS n FROM timesheet_evidence_members").fetchone()["n"] == before
        assert c.execute("SELECT count(*) AS n FROM work_interval_evidence").fetchone()["n"] == 0


def make_legacy(c):
    c.execute("""INSERT INTO work_interval_evidence SELECT * FROM effective_work_interval_evidence""")
    c.execute("UPDATE work_intervals SET evidence_set_id=NULL")
    c.commit()


def test_resumable_backfill_and_reclaim_preserve_every_membership(archive):
    with database(archive) as c:
        expected = c.execute("SELECT * FROM effective_work_interval_evidence ORDER BY 1,2").fetchall()
        make_legacy(c)
        # Exercise predecessor fingerprints and pre-existing shared set registration.
        c.execute("UPDATE timesheet_evidence_sets SET fingerprint='legacy:'||id::text")
        c.commit()
        prepare_shared_sets(c)
        first = backfill_batch(c, 1)
        assert first["intervals"] == 1
        assert verify(c)["uncertified_intervals"] > 0
        # Resume from zero; certificates skip completed intervals safely.
        while backfill_batch(c, 1)["intervals"]:
            pass
        assert verify(c) == {"uncertified_intervals": 0, "invalid_sets": 0}
        reclaim(c)
        actual = c.execute("SELECT * FROM effective_work_interval_evidence ORDER BY 1,2").fetchall()
        assert actual == expected
        assert c.execute("SELECT count(*) AS n FROM work_interval_evidence").fetchone()["n"] == 0
    with pytest.raises(psycopg.errors.RaiseException), database(archive) as c:
        c.execute("INSERT INTO work_interval_evidence SELECT * FROM effective_work_interval_evidence LIMIT 1")


def test_conflicting_membership_stops_without_certifying(archive):
    with database(archive) as c:
        c.execute("INSERT INTO work_interval_evidence SELECT * FROM effective_work_interval_evidence")
        c.execute("UPDATE work_interval_evidence SET episode_key='different'")
        c.commit()
        with pytest.raises(ValueError, match="membership mismatch"):
            backfill_batch(c)
        c.rollback()
        assert c.execute("SELECT count(*) AS n FROM storage_interval_verification").fetchone()["n"] == 0


def test_proof_invalidated_on_legacy_edit_and_shared_members_immutable(archive):
    with database(archive) as c:
        make_legacy(c)
        while backfill_batch(c)["intervals"]:
            pass
        c.execute(
            "UPDATE work_interval_evidence SET episode_key='changed' "
            "WHERE interval_id=(SELECT min(id) FROM work_intervals)"
        )
        c.commit()
        assert verify(c)["uncertified_intervals"] > 0
        with pytest.raises(ValueError, match="complete verification"):
            reclaim(c)
        c.rollback()
    with pytest.raises(psycopg.errors.RaiseException), database(archive) as c:
        c.execute("UPDATE timesheet_evidence_members SET episode_key='changed'")


def test_target_identity_and_concurrent_set_reuse(archive):
    with database(archive) as c:
        token = identity(c)["target"]
        require_target(c, token)
        with pytest.raises(ValueError, match="identity mismatch"):
            require_target(c, "wrong")
        event = c.execute("SELECT min(id) AS id FROM events").fetchone()["id"]

    def insert(_):
        with database(archive) as c:
            return persist_evidence(c, [{"event_id": event, "episode_key": "concurrent"}])

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(insert, range(2)))) == 1


def test_changed_membership_and_settings_make_distinct_identities(archive):
    with database(archive) as c:
        event = c.execute("SELECT min(id) AS id FROM events").fetchone()["id"]
        assert persist_evidence(c, [{"event_id": event, "episode_key": None}]) != persist_evidence(
            c, [{"event_id": event, "episode_key": "episode"}]
        )
        first = build_timesheet(c, cutoff=datetime(2026, 7, 22, tzinfo=UTC))
        c.execute("UPDATE sessions SET contributor_id=NULL")
        second = build_timesheet(c, cutoff=first.cutoff)
        assert second.snapshot_id != first.snapshot_id


def test_existing_shared_schema_upgrade_and_source_preservation(archive):
    from chatreview.db import migrate

    with database(archive) as c:
        raw = c.execute(
            "SELECT payload_hash,encode(sha256(payload),'hex') AS digest FROM raw_payloads ORDER BY 1"
        ).fetchall()
        artifacts = c.execute("SELECT * FROM artifacts ORDER BY id").fetchall()
        snapshots = c.execute(
            "SELECT to_jsonb(s)-'calculation_fingerprint' AS row FROM timesheet_snapshots s ORDER BY id"
        ).fetchall()
        c.execute("DROP VIEW effective_work_interval_evidence")
        c.execute("DROP FUNCTION invalidate_interval_storage_proof() CASCADE")
        c.execute("DROP FUNCTION protect_referenced_evidence_members() CASCADE")
        c.execute("DROP TABLE storage_interval_verification,storage_maintenance_progress")
        c.execute("ALTER TABLE timesheet_snapshots DROP COLUMN calculation_fingerprint")
        c.execute("DROP FUNCTION protect_inserted_evidence_members() CASCADE")
        c.execute("DROP FUNCTION reject_legacy_evidence_writes() CASCADE")
        c.execute("DELETE FROM schema_meta WHERE key='timesheet_legacy_evidence_retired'")
        c.execute("DELETE FROM chatreview_schema_migrations WHERE version>=22")
    migrate(archive)
    with database(archive) as c:
        prepare_shared_sets(c)
        assert verify(c) == {"uncertified_intervals": 0, "invalid_sets": 0}
        assert (
            c.execute(
                "SELECT payload_hash,encode(sha256(payload),'hex') AS digest FROM raw_payloads ORDER BY 1"
            ).fetchall()
            == raw
        )
        assert c.execute("SELECT * FROM artifacts ORDER BY id").fetchall() == artifacts
        assert (
            c.execute(
                "SELECT to_jsonb(s)-'calculation_fingerprint' AS row FROM timesheet_snapshots s ORDER BY id"
            ).fetchall()
            == snapshots
        )


def test_disjoint_parallel_backfill_reuses_identical_sets(archive):
    from chatreview.storage import backfill_range

    with database(archive) as c:
        build_timesheet(c, cutoff=datetime(2026, 7, 21, tzinfo=UTC))
        expected = c.execute("SELECT * FROM effective_work_interval_evidence ORDER BY 1,2").fetchall()
        make_legacy(c)
        c.execute("DELETE FROM timesheet_evidence_members")
        c.execute("DELETE FROM timesheet_evidence_sets")
        maximum = c.execute("SELECT max(id) AS id FROM work_intervals").fetchone()["id"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(backfill_range, archive, low, high, 2)
            for low, high in [(0, maximum // 2), (maximum // 2, maximum)]
        ]
        assert sum(f.result()["intervals"] for f in futures) == maximum
    with database(archive) as c:
        assert verify(c) == {"uncertified_intervals": 0, "invalid_sets": 0}
        assert c.execute("SELECT * FROM effective_work_interval_evidence ORDER BY 1,2").fetchall() == expected


def test_parallel_range_retries_only_transient_rolled_back_batches(archive, monkeypatch):
    import chatreview.storage as storage

    original = storage.backfill_batch
    attempts = 0

    def transient(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise psycopg.errors.LockNotAvailable("concurrent set registration")
        return original(*args, **kwargs)

    monkeypatch.setattr(storage, "backfill_batch", transient)
    monkeypatch.setattr(storage.time, "sleep", lambda _: None)
    with database(archive) as c:
        make_legacy(c)
    result = storage.backfill_range(archive, 0, 10000, 200)
    assert result["intervals"] > 0
    assert attempts >= 3
    with database(archive) as c:
        assert verify(c) == {"uncertified_intervals": 0, "invalid_sets": 0}


def test_calendar_and_exports_preserve_mixed_historical_storage(archive):
    from chatreview.timesheets import export_timesheet, timesheet_calendar

    with database(archive) as c:
        original = timesheet_calendar(c, year=2026)
        exports = {fmt: export_timesheet(c, format=fmt).content for fmt in ('csv', 'markdown', 'json')}
        make_legacy(c)
        assert timesheet_calendar(c, year=2026) == original
        assert backfill_batch(c, 1)['intervals'] == 1
        assert timesheet_calendar(c, year=2026) == original
        for fmt, content in exports.items():
            assert export_timesheet(c, format=fmt).content == content
        while backfill_batch(c, 1)['intervals']:
            pass
        reclaim(c)
        assert timesheet_calendar(c, year=2026) == original
        for fmt, content in exports.items():
            assert export_timesheet(c, format=fmt).content == content


@pytest.mark.parametrize("file_exists", [False, True])
def test_selected_environment_never_falls_back_to_ambient_database(tmp_path, monkeypatch, file_exists):
    from typer.testing import CliRunner

    import chatreview.storage as storage

    selected = tmp_path / "selected.env"
    if file_exists:
        selected.write_text("UNRELATED_SETTING=1\n")
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", "postgresql://ambient.invalid/archive")

    def unexpected_database(*args, **kwargs):
        pytest.fail("Selected environment must fail before opening any database")

    monkeypatch.setattr(storage, "database", unexpected_database)
    result = CliRunner().invoke(storage.app, ["audit", "--env-file", str(selected)])
    assert result.exit_code != 0
    assert "Selected environment file" in result.output


def test_migration_preserves_already_reclaimed_guard(archive):
    from chatreview.db import migrate

    with database(archive) as c:
        c.execute("DELETE FROM chatreview_schema_migrations WHERE version=25")
        c.execute("DELETE FROM schema_meta WHERE key='timesheet_legacy_evidence_retired'")
        c.execute("""CREATE OR REPLACE FUNCTION reject_legacy_evidence_writes()
            RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Legacy timesheet evidence retired'; END $$""")
    migrate(archive)
    with pytest.raises(psycopg.errors.RaiseException), database(archive) as c:
        c.execute("INSERT INTO work_interval_evidence SELECT * FROM effective_work_interval_evidence")


@pytest.mark.parametrize("field,value", [("provider", "git"), ("external_id", "changed-external")])
def test_session_attribution_fields_invalidate_calculation(archive, field, value):
    from chatreview.shared_evidence import calculation_fingerprint

    with database(archive) as c:
        before = calculation_fingerprint(c, "UTC")
        c.execute(f"UPDATE sessions SET {field}=? WHERE id=(SELECT min(id) FROM sessions)", (value,))
        assert calculation_fingerprint(c, "UTC") != before


def test_corrupt_canonical_identity_is_rejected(archive):
    with database(archive) as c:
        c.execute("UPDATE timesheet_evidence_sets SET fingerprint='v1:corrupt' "
                  "WHERE id=(SELECT min(id) FROM timesheet_evidence_sets)")
        c.commit()
        assert verify(c)['invalid_sets'] == 1
        with pytest.raises(ValueError, match="canonical evidence fingerprint mismatch"):
            prepare_shared_sets(c)


def test_legacy_duplicate_keeps_memberships_and_reuses_canonical_set(archive):
    with database(archive) as c:
        original = c.execute(
            "SELECT id,member_count FROM timesheet_evidence_sets ORDER BY id LIMIT 1"
        ).fetchone()
        duplicate = c.execute("INSERT INTO timesheet_evidence_sets(fingerprint,member_count) "
                              "VALUES ('legacy:duplicate',?) RETURNING id",
                              (original['member_count'],)).fetchone()['id']
        c.execute("INSERT INTO timesheet_evidence_members SELECT ?,event_id,episode_key "
                  "FROM timesheet_evidence_members WHERE evidence_set_id=?", (duplicate,original['id']))
        prepare_shared_sets(c)
        members = c.execute("SELECT event_id,episode_key FROM timesheet_evidence_members "
                            "WHERE evidence_set_id=?", (duplicate,)).fetchall()
        assert persist_evidence(c, members) == original['id']
        assert verify(c)['invalid_sets'] == 0


def test_machine_attribution_invalidates_calculation(archive):
    from uuid import uuid4

    from chatreview.shared_evidence import calculation_fingerprint

    with database(archive) as c:
        before = calculation_fingerprint(c, "UTC")
        machine = str(uuid4())
        c.execute("INSERT INTO machines(id,name) VALUES (?, 'synthetic other device')", (machine,))
        c.execute("UPDATE sessions SET machine_id=? WHERE id=(SELECT min(id) FROM sessions)", (machine,))
        assert calculation_fingerprint(c, "UTC") != before
