from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import orjson

from chatreview.db import database
from chatreview.ingest import sync_sources

SESSION_ID = "33333333-3333-3333-3333-333333333333"


def _settings_with_codex_roots(settings, *roots: Path):
    """Keep the ingest test explicitly scoped to the configured Codex roots."""

    return replace(
        settings,
        codex_roots=tuple(root.resolve() for root in roots),
        claude_roots=(),
        gemini_roots=(),
        git_roots=(),
    )


def _write_codex_session(path: Path, session_id: str, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "timestamp": "2026-07-19T02:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "session_id": session_id,
                "cwd": "/work/multi-root-project",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": "2026-07-19T02:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": message}],
            },
        },
    ]
    path.write_bytes(b"\n".join(orjson.dumps(record) for record in records) + b"\n")


def test_sync_sources_ingests_two_codex_roots_and_is_idempotent(corpus) -> None:
    settings, _, _ = corpus
    second_root = settings.data_dir.parent / "second-codex-root"
    second_session = (
        second_root
        / "sessions"
        / "2026"
        / "07"
        / "33333333-3333-3333-3333-333333333333.jsonl"
    )
    _write_codex_session(second_session, SESSION_ID, "A session from the second Codex root")
    settings = _settings_with_codex_roots(settings, settings.codex_root, second_root)

    first = sync_sources(settings, providers={"codex"})

    assert first.discovered_files == 3
    assert first.processed_files == 3
    with database(settings.database_url, read_only=True) as connection:
        source_rows = connection.execute(
            "SELECT path FROM sources WHERE machine_id=? AND provider='codex'",
            (settings.machine_id,),
        ).fetchall()
        event_count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    assert {Path(row["path"]) for row in source_rows} == {
        settings.codex_root / "history.jsonl",
        settings.codex_root
        / "sessions"
        / "2026"
        / "07"
        / "18"
        / "rollout-2026-07-18T10-00-00-11111111-1111-1111-1111-111111111111.jsonl",
        second_session.resolve(),
    }

    second = sync_sources(settings, providers={"codex"})

    assert second.discovered_files == 3
    assert second.processed_files == 0
    assert second.skipped_files == 3
    with database(settings.database_url, read_only=True) as connection:
        assert int(connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]) == len(
            source_rows
        )
        assert int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]) == event_count


def test_copied_codex_session_uses_one_session_with_two_source_provenances(corpus) -> None:
    settings, codex_session, _ = corpus
    second_root = settings.data_dir.parent / "copied-codex-root"
    copied_session = (
        second_root
        / "sessions"
        / "2026"
        / "07"
        / "copied-11111111-1111-1111-1111-111111111111.jsonl"
    )
    copied_session.parent.mkdir(parents=True, exist_ok=True)
    copied_session.write_bytes(codex_session.read_bytes())
    settings = _settings_with_codex_roots(settings, settings.codex_root, second_root)

    sync_sources(settings, providers={"codex"})

    with database(settings.database_url, read_only=True) as connection:
        sessions = connection.execute(
            """
            SELECT id
            FROM sessions
            WHERE provider='codex' AND external_id=?
            """,
            ("11111111-1111-1111-1111-111111111111",),
        ).fetchall()
        assert len(sessions) == 1
        session_id = int(sessions[0]["id"])
        linked_session_paths = connection.execute(
            """
            SELECT source.path
            FROM session_sources link
            JOIN sources source ON source.id=link.source_id
            WHERE link.session_id=? AND source.source_kind='session'
            """,
            (session_id,),
        ).fetchall()

    assert {Path(row["path"]) for row in linked_session_paths} == {
        codex_session.resolve(),
        copied_session.resolve(),
    }
