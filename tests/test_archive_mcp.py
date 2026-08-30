from __future__ import annotations

from chatreview.archive_mcp import ArchiveReader
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter


def test_archive_reader_is_bounded_and_read_only(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    reader = ArchiveReader(settings.database_url)

    status = reader.status()
    sessions = reader.sessions(limit=500)

    assert status["sessions"] >= 1
    assert 1 <= len(sessions) <= 50
    assert settings.database_url not in repr(status)
    assert settings.database_url not in repr(sessions)
    assert reader.trace(sessions[0]["id"])["session"]["id"] == sessions[0]["id"]
