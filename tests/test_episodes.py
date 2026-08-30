from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import orjson

from chatreview.api import create_app
from chatreview.db import database
from chatreview.episodes import (
    EpisodeBuilder,
    EventRecord,
    UnitRecord,
    _render_episode,
    _segment_events,
    get_episode,
    list_episodes,
)
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.reporting import build_baseline_report
from chatreview.search import lexical_search


def _ingestor(settings):
    return Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    )


def test_copied_machine_prefix_keeps_one_logical_occurrence_identity(
    corpus, tmp_path: Path
) -> None:
    settings, _, _ = corpus
    _ingestor(settings).run()
    EpisodeBuilder(settings).run(force=True)
    with database(settings.database_url, read_only=True) as connection:
        original_keys = {
            row["episode_key"] for row in connection.execute("SELECT episode_key FROM episodes")
        }

    copied_root = tmp_path / "copied-codex"
    shutil.copytree(settings.codex_root, copied_root)
    copied_settings = replace(
        settings,
        machine_id=UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        machine_name="copied-machine",
        codex_root=copied_root,
        codex_history=copied_root / "history.jsonl",
    )
    Ingestor(copied_settings, [CodexAdapter(copied_root)]).run()
    rebuilt = EpisodeBuilder(copied_settings).run(force=True)
    with database(settings.database_url, read_only=True) as connection:
        rebuilt_keys = {
            row["episode_key"] for row in connection.execute("SELECT episode_key FROM episodes")
        }
        duplicate_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE canonical_event_id IS NOT NULL"
        ).fetchone()[0]
        logical_hits = lexical_search(connection, "frobnicator keeps failing")
    assert rebuilt.canonical.duplicate_events > 0
    assert duplicate_count > 0
    assert len(logical_hits) == 1
    assert rebuilt_keys == original_keys


def test_episode_derivation_canonicalizes_echoes_and_preserves_evidence(corpus) -> None:
    settings, codex_session, _ = corpus
    with codex_session.open("ab") as handle:
        handle.write(
            orjson.dumps(
                {
                    "timestamp": "2026-07-18T02:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "Fatal error: frobnicator exploded",
                    },
                }
            )
            + b"\n"
        )
    _ingestor(settings).run()
    summary = EpisodeBuilder(settings).run()

    assert summary.episodes == 2
    assert summary.error_episodes == 2
    assert summary.canonical.duplicate_events == 1
    assert EpisodeBuilder(settings).run().reused is True

    with database(settings.database_url, read_only=True) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM events WHERE canonical_event_id IS NOT NULL").fetchone()[
                0
            ]
            == 1
        )
        episodes = list_episodes(connection, query="frobnicator", errors_only=True)
        assert len(episodes) == 1
        episode = get_episode(connection, episodes[0]["id"])
        assert episode is not None
        assert "[GOAL]" in episode["document"]
        assert "[ATTEMPTS]" in episode["document"]
        assert "[ERROR EVIDENCE]" in episode["document"]
        assert episode["attempt_count"] == 1
        report = build_baseline_report(connection, top=10, min_sessions=1)
        assert "Goal-attempt-result episodes" in report
        assert "Excluded raw hits" in report
        assert "Fatal error: frobnicator exploded" in report


def test_episode_derivation_rebuilds_only_the_changed_session(corpus) -> None:
    settings, codex_session, _ = corpus
    _ingestor(settings).run()
    initial = EpisodeBuilder(settings).run()
    assert initial.rebuilt_sessions == 2

    with database(settings.database_url, read_only=True) as connection:
        generation = connection.execute(
            "SELECT value FROM schema_meta WHERE key='episode_generation'"
        ).fetchone()["value"]
        before = {
            row["provider"]: [int(value) for value in row["episode_ids"]]
            for row in connection.execute(
                """
                SELECT session.provider, array_agg(episode.id ORDER BY episode.id) AS episode_ids
                FROM episodes episode
                JOIN sessions session ON session.id=episode.session_id
                GROUP BY session.provider
                """
            ).fetchall()
        }

    with codex_session.open("ab") as handle:
        handle.write(
            orjson.dumps(
                {
                    "timestamp": "2026-07-18T02:00:05Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "Document the repaired frobnicator"}
                        ],
                    },
                }
            )
            + b"\n"
        )

    _ingestor(settings).run()
    incremental = EpisodeBuilder(settings).run()
    assert incremental.rebuilt_sessions == 1
    assert incremental.reused_sessions == 1

    with database(settings.database_url, read_only=True) as connection:
        assert (
            connection.execute(
                "SELECT value FROM schema_meta WHERE key='episode_generation'"
            ).fetchone()["value"]
            == generation
        )
        after = {
            row["provider"]: [int(value) for value in row["episode_ids"]]
            for row in connection.execute(
                """
                SELECT session.provider, array_agg(episode.id ORDER BY episode.id) AS episode_ids
                FROM episodes episode
                JOIN sessions session ON session.id=episode.session_id
                GROUP BY session.provider
                """
            ).fetchall()
        }
        assert int(
            connection.execute("SELECT COUNT(*) FROM episode_session_state").fetchone()[0]
        ) == 2

    assert after["claude"] == before["claude"]
    assert after["codex"] != before["codex"]
    assert EpisodeBuilder(settings).run().reused is True


def test_episode_api_lists_and_opens_derived_episode(corpus) -> None:
    settings, _, _ = corpus
    _ingestor(settings).run()
    EpisodeBuilder(settings).run()

    from fastapi.testclient import TestClient

    client = TestClient(create_app(settings))
    stats = client.get("/api/episodes/stats")
    assert stats.status_code == 200
    assert stats.json()["episodes"] == 2
    listed = client.get("/api/episodes", params={"errors_only": True})
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    detail = client.get(f"/api/episodes/{listed.json()[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["events"]
    assert detail.json()["fingerprints"]


def test_repeated_identical_goals_remain_distinct_episodes(corpus) -> None:
    settings, codex_session, _ = corpus
    with codex_session.open("ab") as handle:
        for timestamp, call_id in [
            ("2026-07-19T02:00:00Z", "repeat-1"),
            ("2026-07-20T02:00:00Z", "repeat-2"),
        ]:
            records = [
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Retry identical goal"}],
                    },
                },
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "exec_command",
                        "arguments": '{"cmd":"make retry"}',
                        "call_id": call_id,
                    },
                },
            ]
            for record in records:
                handle.write(orjson.dumps(record) + b"\n")
    _ingestor(settings).run()
    summary = EpisodeBuilder(settings).run()
    assert summary.episodes == 4
    with database(settings.database_url, read_only=True) as connection:
        rows = list_episodes(connection, query="Retry identical goal")
        assert len(rows) == 2
        assert rows[0]["episode_key"] != rows[1]["episode_key"]


def test_successful_tool_output_containing_error_code_is_not_failure_evidence(corpus) -> None:
    settings, codex_session, _ = corpus
    with codex_session.open("ab") as handle:
        for record in [
            {
                "timestamp": "2026-07-19T02:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Inspect logging source"}],
                },
            },
            {
                "timestamp": "2026-07-19T02:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "inspect-source",
                    "output": ('Exit code: 0\nOutput:\nlogger.error(f"Query execution failed: {error}")'),
                },
            },
        ]:
            handle.write(orjson.dumps(record) + b"\n")
    _ingestor(settings).run()
    summary = EpisodeBuilder(settings).run()
    assert summary.error_episodes == 2
    with database(settings.database_url, read_only=True) as connection:
        episode = list_episodes(connection, query="Inspect logging source")[0]
        assert episode["error_count"] == 0
        error_fingerprints = connection.execute(
            """
            SELECT COUNT(*) FROM episode_fingerprints
            WHERE episode_id=? AND kind='error-signature'
            """,
            (episode["id"],),
        ).fetchone()[0]
        assert error_fingerprints == 0


def test_provider_request_ids_and_injected_context_do_not_create_episode_boundaries() -> None:
    def event(
        event_id: int,
        kind: str,
        text: str,
        turn_id: str,
        timestamp: str,
    ) -> EventRecord:
        return EventRecord(
            id=event_id,
            event_key=f"event-{event_id}",
            event_fingerprint=None,
            timestamp=timestamp,
            event_type="response_item",
            subtype="message",
            role="user" if kind == "user-message" else "assistant",
            turn_id=turn_id,
            units=[UnitRecord(kind, None, text, False)],
        )

    drafts = _segment_events(
        [
            event(
                1,
                "user-message",
                (
                    '<codex_internal_context source="goal">\n'
                    "<objective>Repair every parser family</objective>\n"
                    "Continuation behavior: keep going"
                ),
                "turn-a",
                "2026-07-18T01:00:00Z",
            ),
            event(
                2,
                "user-message",
                "<environment_context>injected</environment_context>",
                "turn-a",
                "2026-07-18T01:00:01Z",
            ),
            event(3, "user-message", "Fix the actual parser failure", "turn-b", "2026-07-18T01:00:02Z"),
            event(4, "assistant-message", "I will inspect it", "request-1", "2026-07-18T01:00:03Z"),
            event(5, "reasoning", "Trace the input", "request-2", "2026-07-18T01:00:04Z"),
            event(6, "user-message", "Now verify the repair", "turn-c", "2026-07-18T01:00:05Z"),
        ]
    )

    assert len(drafts) == 2
    first = _render_episode(drafts[0].events)
    assert first["goal"] == "Fix the actual parser failure"
    assert "[OBJECTIVE]\nRepair every parser family" in first["document"]
    assert "Continuation behavior" not in first["document"]
    assert "environment_context" not in first["document"]
    assert len(drafts[0].events) == 5


def test_claude_subagent_file_is_segmented_as_an_independent_track(corpus) -> None:
    settings, _, claude_session = corpus
    subagent = claude_session.with_suffix("") / "subagents" / "agent-a-test.jsonl"
    subagent.parent.mkdir(parents=True)
    records = [
        {
            "type": "user",
            "uuid": "sub-msg-1",
            "sessionId": "22222222-2222-2222-2222-222222222222",
            "timestamp": "2026-07-18T03:00:00.500Z",
            "cwd": "/work/claude-project",
            "message": {"role": "user", "content": "Independently audit the database"},
        },
        {
            "type": "assistant",
            "uuid": "sub-msg-2",
            "parentUuid": "sub-msg-1",
            "sessionId": "22222222-2222-2222-2222-222222222222",
            "timestamp": "2026-07-18T03:00:01.500Z",
            "cwd": "/work/claude-project",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "sub-tool-1",
                        "name": "Bash",
                        "input": {"command": "check-database"},
                    }
                ],
            },
        },
    ]
    with subagent.open("wb") as handle:
        for record in records:
            handle.write(orjson.dumps(record) + b"\n")

    _ingestor(settings).run()
    summary = EpisodeBuilder(settings).run()

    assert summary.episodes == 3
    with database(settings.database_url, read_only=True) as connection:
        parent = list_episodes(connection, query="widget still broken")
        child = list_episodes(connection, query="Independently audit database")
        assert len(parent) == 1
        assert len(child) == 1
        assert "Independently audit" not in parent[0]["document"]
        assert "widget is still broken" not in child[0]["document"]
