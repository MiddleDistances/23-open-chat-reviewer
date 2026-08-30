from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import orjson
from fastapi.testclient import TestClient

from chatreview.api import create_app
from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import GeminiAdapter
from chatreview.search import lexical_search, read_raw_event


def _write_document(path: Path, value: object) -> bytes:
    payload = orjson.dumps(value, option=orjson.OPT_INDENT_2) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _gemini_fixture(root: Path) -> tuple[Path, Path, bytes]:
    project = root / "tmp" / "project-storage"
    project.mkdir(parents=True)
    (project / ".project_root").write_text("/work/gemini-project\n", encoding="utf-8")
    session = project / "chats" / "session-2026-08-20T01-02-abcd1234.json"
    payload = _write_document(
        session,
        {
            "sessionId": "gemini-session-real-id",
            "projectHash": "project-storage",
            "startTime": "2026-08-20T01:02:03.000Z",
            "lastUpdated": "2026-08-20T01:02:08.000Z",
            "summary": "Fixture session summary",
            "messages": [
                {
                    "id": "gemini-user-message-id",
                    "timestamp": "2026-08-20T01:02:04.000Z",
                    "type": "user",
                    "content": "Inspect the quartz widget",
                },
                {
                    "id": "gemini-system-message-id",
                    "timestamp": "2026-08-20T01:02:05.000Z",
                    "type": "system",
                    "content": "Use the project instructions",
                },
                {
                    "id": "gemini-assistant-message-id",
                    "timestamp": "2026-08-20T01:02:06.000Z",
                    "type": "gemini",
                    "model": "gemini-fixture-model",
                    "content": [
                        {"text": "The quartz widget needs one repair"},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": "a" * 2_000,
                            }
                        },
                    ],
                    "thoughts": [
                        {
                            "subject": "Inspection",
                            "description": "Checked the explicit fixture evidence",
                            "timestamp": "2026-08-20T01:02:06.100Z",
                        }
                    ],
                    "toolCalls": [
                        {
                            "name": "read_file",
                            "args": {"path": "/work/gemini-project/widget.txt"},
                            "result": [
                                {
                                    "functionResponse": {
                                        "name": "read_file",
                                        "response": {"output": "widget contents"},
                                    }
                                }
                            ],
                            "status": "success",
                        }
                    ],
                },
                {
                    "id": "gemini-error-message-id",
                    "timestamp": "2026-08-20T01:02:07.000Z",
                    "type": "error",
                    "content": "Fixture tool error",
                },
            ],
        },
    )
    history = project / "logs.json"
    _write_document(
        history,
        [
            {
                "sessionId": "gemini-session-real-id",
                "messageId": 42,
                "timestamp": "2026-08-20T01:02:04.000Z",
                "type": "user",
                "message": "Inspect the quartz widget",
            }
        ],
    )
    return session, history, payload


def test_gemini_discovers_and_projects_real_document_shapes(tmp_path: Path) -> None:
    root = tmp_path / "gemini"
    session, history, _ = _gemini_fixture(root)
    adapter = GeminiAdapter(root)

    sources = adapter.discover()
    assert {(source.path, source.source_kind) for source in sources} == {
        (history, "history"),
        (session, "session"),
    }
    assert all(adapter.record_format(source) == "json-document" for source in sources)

    session_source = next(source for source in sources if source.source_kind == "session")
    history_source = next(source for source in sources if source.source_kind == "history")
    records = adapter.parse_many(orjson.loads(session.read_bytes()), session_source)
    assert len(records) == 5
    assert {record.provider_event_id for record in records} >= {
        "gemini-user-message-id",
        "gemini-system-message-id",
        "gemini-assistant-message-id",
        "gemini-error-message-id",
    }
    assert {record.role for record in records} >= {None, "user", "system", "assistant"}
    assert all(record.session_external_id == "gemini-session-real-id" for record in records)
    assert all(record.cwd == "/work/gemini-project" for record in records)
    fragments = [fragment for record in records for fragment in record.fragments]
    assert {fragment.kind for fragment in fragments} >= {
        "reasoning-summary",
        "tool-input",
        "tool-output",
        "attachment",
    }
    assert all("a" * 100 not in fragment.text for fragment in fragments)

    history_records = adapter.parse_many(orjson.loads(history.read_bytes()), history_source)
    assert history_records[0].provider_event_id == "history:gemini-session-real-id:42"
    assert history_records[0].timestamp == "2026-08-20T01:02:04.000Z"


def test_gemini_sync_preserves_documents_and_is_idempotent(corpus, tmp_path: Path) -> None:
    settings, _, _ = corpus
    root = tmp_path / "gemini-live"
    session, _, original_payload = _gemini_fixture(root)
    settings = replace(settings, gemini_root=root)
    ingestor = Ingestor(settings, [GeminiAdapter(root)], batch_lines=10)

    first = ingestor.run()
    assert first.discovered_files == 2
    assert first.processed_files == 2
    assert first.events == 6
    assert first.parse_errors == 0

    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 6
        raw_payload = connection.execute(
            """
            SELECT payload.payload FROM raw_payloads payload
            JOIN raw_records raw ON raw.payload_hash=payload.payload_hash
            JOIN source_revisions revision ON revision.id=raw.source_revision_id
            JOIN sources source ON source.id=revision.source_id
            WHERE source.path=?
            """,
            (str(session),),
        ).fetchone()[0]
        assert bytes(raw_payload) == original_payload
        event_id = connection.execute(
            "SELECT id FROM events WHERE provider_event_id='gemini-assistant-message-id'"
        ).fetchone()[0]
        raw = read_raw_event(connection, event_id)
        assert raw is not None and raw["valid"] is True
        assert orjson.loads(raw["raw"])["sessionId"] == "gemini-session-real-id"
        assert raw["source_provenance"]["project_root"] == "/work/gemini-project"
        assert lexical_search(connection, "explicit fixture evidence")

    client = TestClient(create_app(settings))
    raw_response = client.get(
        f"/api/events/{event_id}/raw", params={"as_text": True}
    )
    assert raw_response.status_code == 200
    assert raw_response.headers["content-type"].startswith("application/json")
    session_id = next(
        item["id"] for item in client.get("/api/sessions").json() if item["provider"] == "gemini"
    )
    api_events = client.get(f"/api/sessions/{session_id}/events").json()
    assert api_events[0]["source_provenance"]["project_root"] == "/work/gemini-project"

    second = ingestor.run()
    assert second.skipped_files == 2
    assert second.events == 0
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_revisions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 6


def test_gemini_replacement_and_truncation_open_revisions(corpus, tmp_path: Path) -> None:
    settings, _, _ = corpus
    root = tmp_path / "gemini-revisions"
    session, _, _ = _gemini_fixture(root)
    settings = replace(settings, gemini_root=root)
    ingestor = Ingestor(settings, [GeminiAdapter(root)])
    ingestor.run()

    document = orjson.loads(session.read_bytes())
    document["messages"][0]["content"] = "Replacement marker with comparable payload length"
    _write_document(session, document)
    replacement = ingestor.run()
    assert replacement.reparsed_files == 1

    document["messages"] = document["messages"][:1]
    _write_document(session, document)
    truncation = ingestor.run()
    assert truncation.reparsed_files == 1

    unchanged = ingestor.run()
    assert unchanged.events == 0
    with database(settings.database_url, read_only=True) as connection:
        statuses = [
            row["status"]
            for row in connection.execute(
                """
                SELECT revision.status FROM source_revisions revision
                JOIN sources source ON source.id=revision.source_id
                WHERE source.path=? ORDER BY revision.revision_no
                """,
                (str(session),),
            ).fetchall()
        ]
        assert statuses == ["replaced", "truncated", "complete"]
        assert lexical_search(connection, "quartz widget")
        assert lexical_search(connection, "comparable payload length")


def test_gemini_project_provenance_survives_archive_only_rebuild(corpus, tmp_path: Path) -> None:
    settings, _, _ = corpus
    root = tmp_path / "gemini-provenance"
    session, _, _ = _gemini_fixture(root)
    settings = replace(settings, gemini_root=root)
    Ingestor(settings, [GeminiAdapter(root)]).run()

    marker = session.parent.parent / ".project_root"
    marker.unlink()
    with database(settings.database_url) as connection:
        provenance = connection.execute(
            """
            SELECT revision.provenance_json
            FROM source_revisions revision
            JOIN sources source ON source.id=revision.source_id
            WHERE source.path=?
            """,
            (str(session),),
        ).fetchone()[0]
        assert provenance["project_root"] == "/work/gemini-project"
        assert provenance["evidence_kind"] == "project-root-marker"
        connection.execute(
            "UPDATE sessions SET project=NULL, cwd=NULL WHERE provider='gemini'"
        )

    Ingestor(settings, [GeminiAdapter(root)]).rebuild_from_archive()
    with database(settings.database_url, read_only=True) as connection:
        rebuilt = connection.execute(
            "SELECT project, cwd FROM sessions WHERE provider='gemini'"
        ).fetchall()
    assert rebuilt
    assert {(row["project"], row["cwd"]) for row in rebuilt} == {
        ("/work/gemini-project", "/work/gemini-project")
    }


def test_incomplete_gemini_document_remains_pending_until_valid(corpus, tmp_path: Path) -> None:
    settings, _, _ = corpus
    root = tmp_path / "gemini-partial"
    session = root / "tmp" / "project-storage" / "chats" / "session-partial.json"
    session.parent.mkdir(parents=True)
    partial_payload = b'{"sessionId":"partial-session","messages":['
    session.write_bytes(partial_payload)
    settings = replace(settings, gemini_root=root)
    ingestor = Ingestor(settings, [GeminiAdapter(root)])

    first = ingestor.run()
    assert first.parse_errors == 0
    with database(settings.database_url, read_only=True) as connection:
        revision = connection.execute(
            """
            SELECT revision.status, revision.pending_length, revision.pending_hash
            FROM source_revisions revision
            JOIN sources source ON source.id=revision.source_id
            WHERE source.path=?
            """,
            (str(session),),
        ).fetchone()
        assert revision["status"] == "partial"
        assert revision["pending_length"] == len(partial_payload)
        assert revision["pending_hash"]
        assert connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0

    unchanged_partial = ingestor.run()
    assert unchanged_partial.parse_errors == 0
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM source_revisions").fetchone()[0] == 1

    _write_document(
        session,
        {
            "sessionId": "partial-session",
            "projectHash": "project-storage",
            "startTime": "2026-08-20T01:02:03.000Z",
            "messages": [],
        },
    )
    second = ingestor.run()
    assert second.parse_errors == 0
    with database(settings.database_url, read_only=True) as connection:
        statuses = connection.execute(
            """
            SELECT revision.status
            FROM source_revisions revision
            JOIN sources source ON source.id=revision.source_id
            WHERE source.path=? ORDER BY revision.revision_no
            """,
            (str(session),),
        ).fetchall()
        assert [row["status"] for row in statuses] == ["replaced", "complete"]
        assert connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
