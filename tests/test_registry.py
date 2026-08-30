from __future__ import annotations

from chatreview.db import Session, database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.registry import rebuild_registry


def test_registry_rebuild_is_set_complete_and_alias_idempotent(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        connection.execute(
            """
            INSERT INTO sessions(session_key, provider, external_id, cwd)
            VALUES ('imported-session', 'imported', 'imported-session', '/archive/imported')
            """
        )

    execute_calls = 0
    original_execute = Session.execute

    def counted_execute(self, query, parameters=None):
        nonlocal execute_calls
        execute_calls += 1
        return original_execute(self, query, parameters)

    monkeypatch.setattr(Session, "execute", counted_execute)
    with database(settings.database_url) as connection:
        before = int(connection.execute("SELECT count(*) FROM project_aliases").fetchone()[0])
        execute_calls = 0
        first = rebuild_registry(connection)
        first_rebuild_calls = execute_calls
        after_first = int(
            connection.execute("SELECT count(*) FROM project_aliases").fetchone()[0]
        )
        second = rebuild_registry(connection)
        after_second = int(
            connection.execute("SELECT count(*) FROM project_aliases").fetchone()[0]
        )
        unresolved = int(
            connection.execute("SELECT count(*) FROM sessions WHERE project_id IS NULL").fetchone()[0]
        )

    assert after_first == before + 1
    assert after_second == after_first
    assert first.aliases == second.aliases == after_first
    assert unresolved == 0
    # One bounded statement registers provider-neutral Git path aliases before
    # chat-session resolution; the rebuild remains set-complete rather than row-wise.
    assert first_rebuild_calls <= 7
