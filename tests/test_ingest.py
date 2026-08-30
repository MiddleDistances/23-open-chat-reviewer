from __future__ import annotations

from datetime import date

import orjson

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.search import lexical_search, read_raw_event


def make_ingestor(settings):
    return Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
        batch_lines=2,
    )


def test_ingestion_is_complete_searchable_and_idempotent(corpus) -> None:
    settings, _, _ = corpus
    first = make_ingestor(settings).run()
    assert first.discovered_files == 4
    assert first.processed_files == 4
    assert first.events == 10
    assert first.parse_errors == 1
    assert first.text_units >= 9

    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 10
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 4
        assert connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 10
        assert connection.execute("SELECT COUNT(*) FROM artifacts WHERE kind='command'").fetchone()[0] == 2
        results = lexical_search(connection, "frobnicator failing")
        assert results
        assert results[0]["provider"] == "codex"

    second = make_ingestor(settings).run()
    assert second.skipped_files == 4
    assert second.events == 0
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 10


def test_prune_orphan_contents_keeps_referenced_projection_content(corpus) -> None:
    settings, _, _ = corpus
    ingestor = make_ingestor(settings)
    ingestor.run()
    with database(settings.database_url) as connection:
        before = int(connection.execute("SELECT COUNT(*) FROM contents").fetchone()[0])
        connection.execute(
            "INSERT INTO contents(content_hash, text, char_count) VALUES (?, ?, ?)",
            ("orphan-content-hash", "temporary orphan", len("temporary orphan")),
        )
        assert int(connection.execute("SELECT COUNT(*) FROM contents").fetchone()[0]) == before + 1
        ingestor._prune_orphan_contents(connection)
        assert int(connection.execute("SELECT COUNT(*) FROM contents").fetchone()[0]) == before


def test_history_scope_filters_before_raw_persistence_and_keeps_aggregates(corpus) -> None:
    settings, _, _ = corpus
    summary = make_ingestor(settings).run(
        history_since=date(2026, 7, 18),
        history_until=date(2026, 7, 18),
    )

    assert summary.discovered_files == 3
    assert summary.excluded_files == 1
    assert summary.aggregate_files == 2
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 7
        assert not connection.execute(
            "SELECT 1 FROM sources WHERE path LIKE '%22222222-2222-2222-2222-222222222222.jsonl'"
        ).fetchone()


def test_history_scope_is_applied_before_deterministic_sharding(corpus) -> None:
    settings, _, _ = corpus
    summaries = [
        make_ingestor(settings).run(
            history_since="2026-07-18",
            history_until="2026-07-18",
            shard_index=index,
            shard_count=2,
        )
        for index in range(2)
    ]

    assert sum(summary.discovered_files for summary in summaries) == 3
    assert max(summary.excluded_files for summary in summaries) == 1
    assert max(summary.aggregate_files for summary in summaries) == 2
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 3


def test_append_resumes_without_reparsing(corpus) -> None:
    settings, codex_session, _ = corpus
    make_ingestor(settings).run()
    with codex_session.open("ab") as handle:
        handle.write(
            orjson.dumps(
                {
                    "timestamp": "2026-07-18T02:00:04Z",
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "A new appended conclusion"},
                }
            )
            + b"\n"
        )
    summary = make_ingestor(settings).run(providers={"codex"})
    assert summary.processed_files == 1
    assert summary.reparsed_files == 0
    assert summary.events == 1
    with database(settings.database_url, read_only=True) as connection:
        assert lexical_search(connection, "appended conclusion")


def test_raw_provenance_round_trip(corpus) -> None:
    settings, _, _ = corpus
    make_ingestor(settings).run()
    with database(settings.database_url, read_only=True) as connection:
        event_id = connection.execute(
            "SELECT id FROM events WHERE event_type='response_item' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        raw = read_raw_event(connection, event_id)
    assert raw is not None
    assert raw["available"] is True
    assert raw["valid"] is True
    assert orjson.loads(raw["raw"])["type"] == "response_item"


def test_replaced_source_opens_a_revision_without_losing_history(corpus) -> None:
    settings, _, claude_session = corpus
    make_ingestor(settings).run()
    original = claude_session.read_bytes()
    claude_session.write_bytes(original.replace(b"widget is still broken", b"widget is now different"))
    summary = make_ingestor(settings).run(providers={"claude"})
    assert summary.reparsed_files == 1
    with database(settings.database_url, read_only=True) as connection:
        assert lexical_search(connection, "widget different")
        assert lexical_search(connection, '"still broken"')
        assert connection.execute("SELECT COUNT(*) FROM source_revisions").fetchone()[0] == 5


def test_incomplete_final_line_remains_pending_until_completed(corpus) -> None:
    settings, codex_session, _ = corpus
    make_ingestor(settings).run()
    partial = orjson.dumps(
        {
            "timestamp": "2026-07-18T02:00:04Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "pending line completed"},
        }
    )
    split = len(partial) // 2
    with codex_session.open("ab") as handle:
        handle.write(partial[:split])

    first = make_ingestor(settings).run(providers={"codex"})
    assert first.events == 0
    with database(settings.database_url, read_only=True) as connection:
        revision = connection.execute(
            """
            SELECT revision.status, revision.pending_length, revision.ingested_lines
            FROM sources source
            JOIN source_revisions revision ON revision.id=source.active_revision_id
            WHERE source.path=?
            """,
            (str(codex_session),),
        ).fetchone()
        assert revision["status"] == "partial"
        assert revision["pending_length"] == split
        assert revision["ingested_lines"] == 5

    with codex_session.open("ab") as handle:
        handle.write(partial[split:] + b"\n")
    second = make_ingestor(settings).run(providers={"codex"})
    assert second.events == 1
    with database(settings.database_url, read_only=True) as connection:
        revision = connection.execute(
            """
            SELECT revision.status, revision.pending_length, revision.ingested_lines
            FROM sources source
            JOIN source_revisions revision ON revision.id=source.active_revision_id
            WHERE source.path=?
            """,
            (str(codex_session),),
        ).fetchone()
        assert revision["status"] == "complete"
        assert revision["pending_length"] == 0
        assert revision["ingested_lines"] == 6
        assert lexical_search(connection, "pending line completed")


def test_nul_characters_stay_exact_in_raw_bytes_and_are_safe_in_projections(corpus) -> None:
    settings, codex_session, _ = corpus
    with codex_session.open("ab") as handle:
        handle.write(
            orjson.dumps(
                {
                    "timestamp": "2026-07-18T02:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-nul",
                        "output": "before NUL\x00after NUL",
                    },
                }
            )
            + b"\n"
        )
    summary = make_ingestor(settings).run(providers={"codex"})
    assert summary.events == 7
    with database(settings.database_url, read_only=True) as connection:
        row = connection.execute(
            """
            SELECT event.id, content.text
            FROM events event
            JOIN text_units unit ON unit.event_id=event.id
            JOIN contents content ON content.id=unit.content_id
            WHERE content.text LIKE 'before NUL%'
            """
        ).fetchone()
        assert row is not None
        assert "\x00" not in row["text"]
        raw = read_raw_event(connection, row["id"])
        assert raw is not None
        assert "\\u0000" in raw["raw"]


def test_oversized_text_is_complete_and_searchable_in_bounded_fragments(corpus) -> None:
    settings, codex_session, _ = corpus
    output = ("large tool evidence: " * 70_000) + "terminal_unique_marker"
    with codex_session.open("ab") as handle:
        handle.write(
            orjson.dumps(
                {
                    "timestamp": "2026-07-18T02:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-large",
                        "output": output,
                    },
                }
            )
            + b"\n"
        )
    summary = make_ingestor(settings).run(providers={"codex"})
    assert summary.parse_errors == 1  # the fixture's deliberately invalid JSON record
    with database(settings.database_url, read_only=True) as connection:
        event = connection.execute(
            "SELECT id FROM events WHERE provider_event_id='call-large'"
        ).fetchone()
        assert event is not None
        chunks = connection.execute(
            """
            SELECT content.text FROM text_units unit
            JOIN contents content ON content.id=unit.content_id
            WHERE unit.event_id=? ORDER BY unit.unit_index
            """,
            (event["id"],),
        ).fetchall()
        assert len(chunks) > 1
        assert "".join(row["text"] for row in chunks) == output
        assert lexical_search(connection, "terminal_unique_marker")


def test_parser_upgrade_does_not_create_a_physical_source_revision(corpus) -> None:
    settings, _, _ = corpus
    ingestor = make_ingestor(settings)
    ingestor.run()
    for adapter in ingestor.adapters.values():
        adapter.parser_version += 1
    summary = ingestor.run()
    assert summary.skipped_files == 4
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_revisions").fetchone()[0] == 4


def test_deterministic_source_shards_cover_the_corpus_once(corpus) -> None:
    settings, _, _ = corpus
    summaries = [
        make_ingestor(settings).run(shard_index=index, shard_count=2)
        for index in range(2)
    ]
    assert sum(summary.discovered_files for summary in summaries) == 4
    assert sum(summary.events for summary in summaries) == 10
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 10
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 10
