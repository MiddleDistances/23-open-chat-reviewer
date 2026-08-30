from __future__ import annotations

import orjson
import pytest
from pgvector import Vector

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.semantic import (
    _episode_embedding_text,
    _event_segments,
    _rolling_windows,
    _semantic_profile_clause,
    _vector_list,
    corpus_revision,
    hnsw_recall_at_10,
    map_points,
    semantic_run_freshness,
)


def test_pgvector_wrapper_converts_to_plain_list() -> None:
    assert _vector_list(Vector([0.25, -0.5])) == [0.25, -0.5]


def test_windows_respect_event_boundaries_and_overlap() -> None:
    rows = [
        {"event_id": 1, "role": "user", "kind": "user-message", "event_type": "message", "text": "a" * 30},
        {
            "event_id": 2,
            "role": "assistant",
            "kind": "assistant-message",
            "event_type": "message",
            "text": "b" * 30,
        },
        {"event_id": 3, "role": "user", "kind": "user-message", "event_type": "message", "text": "c" * 30},
    ]
    segments = _event_segments(rows, 70)
    windows = _rolling_windows(segments, max_chars=100, overlap_events=1)
    assert len(windows) >= 2
    assert windows[0]["first_event_id"] == 1
    assert windows[-1]["last_event_id"] == 3
    assert windows[0]["last_event_id"] == windows[1]["first_event_id"]


def test_semantic_profiles_are_bounded_to_conversations_and_occurrences() -> None:
    conversation = _semantic_profile_clause("conversation")
    episodes = _semantic_profile_clause("episodes")

    assert "user-message" in conversation
    assert "tool-input" not in conversation
    assert episodes == "0"
    with pytest.raises(ValueError):
        _semantic_profile_clause("attempts")


def test_episode_embedding_text_bounds_attention_without_losing_sections() -> None:
    document = (
        "[GOAL]\n" + "goal " * 500 + "\n\n"
        "[ATTEMPTS]\n" + "attempt " * 500 + "\n\n"
        "[ERROR EVIDENCE]\n" + "fatal evidence " * 500 + "\n\n"
        "[OUTCOME MESSAGES]\n" + "outcome " * 500
    )
    bounded = _episode_embedding_text(document, max_chars=2_000)
    assert len(bounded) <= 2_000
    assert "[GOAL]" in bounded
    assert "[ATTEMPTS]" in bounded
    assert "[ERROR EVIDENCE]" in bounded
    assert "[OUTCOME MESSAGES]" in bounded


def test_corpus_revision_detects_later_ingestion(postgres_database_url: str) -> None:
    with database(postgres_database_url) as connection:
        connection.execute(
            """
            INSERT INTO machines(id, name)
            VALUES ('11111111-2222-3333-4444-555555555555', 'pytest')
            """
        )
        source = connection.execute(
            """
            INSERT INTO sources(machine_id, provider, path, source_kind)
            VALUES ('11111111-2222-3333-4444-555555555555', 'codex', '/tmp/session.jsonl', 'session')
            RETURNING id
            """
        ).fetchone()
        revision = connection.execute(
            """
            INSERT INTO source_revisions(
                source_id, revision_no, size_bytes, mtime_ns, parser_version,
                ingested_offset, ingested_lines, status
            ) VALUES (?, 1, 100, 1, 2, 100, 3, 'complete') RETURNING id
            """,
            (source["id"],),
        ).fetchone()
        connection.execute(
            "UPDATE sources SET active_revision_id=? WHERE id=?",
            (revision["id"], source["id"]),
        )
        before = corpus_revision(connection)
        current_run = {"config_json": orjson.dumps({"corpus_revision": before}).decode()}
        assert semantic_run_freshness(connection, current_run) == "current"

        connection.execute(
            "UPDATE source_revisions SET size_bytes=140, ingested_offset=140, ingested_lines=4"
        )
        after = corpus_revision(connection)
        assert after != before
        assert semantic_run_freshness(connection, current_run) == "stale"
        assert semantic_run_freshness(connection, {"config_json": "{}"}) == "unknown"


def test_map_points_selects_default_run_without_a_profile(
    postgres_database_url: str,
) -> None:
    with database(postgres_database_url) as connection:
        run = connection.execute(
            """
            INSERT INTO semantic_runs(
                run_key, model_name, model_revision, dimensions, window_chars,
                overlap_events, profile, corpus_fingerprint, derivation_version,
                status, is_active, config_json, completed_at
            ) VALUES (
                'map-default-test', 'test', 'test', 512, 1000, 1,
                'conversation', 'fingerprint', 1, 'complete', true, '{}',
                clock_timestamp()
            ) RETURNING id
            """
        ).fetchone()
        connection.commit()

        result = map_points(connection)

    assert result["run"]["id"] == run["id"]
    assert result["total"] == 0
    assert result["points"] == []


def test_pgvector_hnsw_recall_gate_uses_stored_512_dimension_vectors(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        event = connection.execute(
            """
            SELECT event.id, event.session_id, unit.content_id
            FROM events event JOIN text_units unit ON unit.event_id=event.id
            WHERE event.canonical_event_id IS NULL ORDER BY event.id LIMIT 1
            """
        ).fetchone()
        run = connection.execute(
            """
            INSERT INTO semantic_runs(
                run_key, model_name, model_revision, dimensions, window_chars,
                overlap_events, profile, corpus_fingerprint, derivation_version,
                status, config_json, expected_count, chunk_count
            ) VALUES (
                'recall-test', 'test', 'test', 512, 1000, 1, 'conversation',
                'fingerprint', 1, 'building', '{}', 12, 12
            ) RETURNING id
            """
        ).fetchone()
        vectors: list[list[float]] = []
        for index in range(12):
            vector = [0.0] * 512
            vector[index] = 1.0
            vector[(index + 37) % 512] = 0.25
            vectors.append(vector)
            connection.execute(
                """
                INSERT INTO semantic_windows(
                    run_id, window_key, session_id, first_event_id, last_event_id,
                    sequence_no, content_id, vector_ordinal, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run["id"],
                    f"window-{index}",
                    event["session_id"],
                    event["id"],
                    event["id"],
                    index,
                    event["content_id"],
                    index,
                    vector,
                ),
            )
        connection.commit()
        recall = hnsw_recall_at_10(
            connection, run_id=int(run["id"]), query_vectors=vectors[:4]
        )
    assert recall >= 0.95
