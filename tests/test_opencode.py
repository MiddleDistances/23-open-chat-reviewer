"""Check OpenCode row conservation, live WAL reads, and archive rebuilds."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import orjson

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers.opencode import OpenCodeAdapter


def _source(root: Path) -> sqlite3.Connection:
    root.mkdir()
    connection = sqlite3.connect(root / "opencode.db")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript("""
        CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, parent_id TEXT,
                              title TEXT, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER,
                              time_updated INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                           time_created INTEGER, time_updated INTEGER, data TEXT);
        INSERT INTO session VALUES ('session-1','/work/example','parent-1','Review',
                                    1786894800000,1786894802000);
    """)
    for mid, role in [("msg-1", "user"), ("msg-2", "assistant")]:
        connection.execute(
            "INSERT INTO message VALUES (?,?,1,1,?)",
            (mid, "session-1", orjson.dumps({"role": role, "time": {"created": 1786894801000}}).decode()),
        )
    for pid, mid, part in [
        ("part-1", "msg-1", {"type": "text", "text": "Investigate wobbleprobe"}),
        ("part-2", "msg-2", {"type": "reasoning", "text": "Check the source"}),
        (
            "part-3",
            "msg-2",
            {
                "type": "tool",
                "tool": "bash",
                "callID": "call-1",
                "state": {
                    "status": "error",
                    "input": {"command": "false"},
                    "error": "Error: wobbleprobe failed",
                },
            },
        ),
    ]:
        connection.execute(
            "INSERT INTO part VALUES (?,?,?,1,1,?)", (pid, mid, "session-1", orjson.dumps(part).decode())
        )
    connection.commit()
    return connection


def test_live_wal_export_is_lossless_private_and_repeatable(tmp_path: Path) -> None:
    root = tmp_path / "source"
    with _source(root) as connection:
        before = (root / "opencode.db").read_bytes()
        adapter = OpenCodeAdapter([root, root], tmp_path / "exports")
        sources = adapter.prepare()
        assert len(sources) == 1
        source = sources[0]
        payload = orjson.loads(source.path.read_bytes())
        assert payload["parts"] == [
            dict(
                zip(
                    ["id", "message_id", "session_id", "time_created", "time_updated", "data"],
                    row,
                    strict=True,
                )
            )
            for row in connection.execute("SELECT * FROM part ORDER BY time_created,id")
        ]
        records = adapter.parse_many(payload, source)
        assert len(records) == 3
        assert records[1].fragments[0].text == "Investigate wobbleprobe"
        assistant = records[2]
        assert assistant.parent_session_external_id == "parent-1"
        assert [(f.kind, f.is_error) for f in assistant.fragments] == [
            ("reasoning", False),
            ("tool-input", False),
            ("tool-output", True),
        ]
        stamp = source.path.stat().st_mtime_ns
        adapter.prepare()
        assert source.path.stat().st_mtime_ns == stamp
        assert source.path.stat().st_mode & 0o077 == 0
        assert (root / "opencode.db").read_bytes() == before
        connection.execute(
            "UPDATE part SET data=? WHERE id='part-1'",
            ('{"type":"text","text":"Investigate wobbleprobe again"}',),
        )
        connection.commit()
        adapter.prepare()
        assert source.path.stat().st_mtime_ns != stamp
        assert "again" in source.path.read_text()
    assert OpenCodeAdapter([], tmp_path / "exports").discover() == []


def test_ingest_search_and_changed_session_retains_revisions(corpus, tmp_path: Path) -> None:
    settings, _, _ = corpus
    root = tmp_path / "opencode"
    settings = replace(settings, opencode_root=root, opencode_roots=(root,))
    with _source(root) as connection:
        adapter = OpenCodeAdapter(root, settings.data_dir / "opencode-sources")
        adapter.prepare()
        ingestor = Ingestor(settings, [adapter])
        first = ingestor.run(providers={"opencode"})
        assert first.parse_errors == 0
        assert first.events == 3
        adapter.prepare()
        assert ingestor.run(providers={"opencode"}).skipped_files == 1
        connection.execute(
            "UPDATE part SET data=? WHERE id='part-1'", ('{"type":"text","text":"Resolved wobbleprobe"}',)
        )
        connection.commit()
        adapter.prepare()
        assert ingestor.run(providers={"opencode"}).parse_errors == 0
    with database(settings.database_url) as archive:
        assert archive.execute("SELECT count(*) AS n FROM events").fetchone()["n"] == 6
        row = archive.execute("SELECT cwd,parent_session_id FROM sessions").fetchone()
        assert row["cwd"] == "/work/example"
        assert row["parent_session_id"] == "parent-1"
        matches = archive.execute(
            "SELECT text FROM contents WHERE text LIKE '%Resolved wobbleprobe%'"
        ).fetchall()
        assert matches
        assert archive.execute("SELECT count(*) AS n FROM source_revisions").fetchone()["n"] == 2
