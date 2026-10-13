"""Regressions for source-scoped derived refreshes on an unchanged archive."""

from chatreview.db import database
from chatreview.episodes import EpisodeBuilder
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter


def test_unchanged_sync_does_not_rewrite_sessions_or_scan_events(corpus, monkeypatch):
    settings, _, _ = corpus

    def ingestor():
        return Ingestor(settings, [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)])

    ingestor().run()
    EpisodeBuilder(settings).run()
    with database(settings.database_url) as connection:
        before = connection.execute("SELECT id,updated_at FROM sessions ORDER BY id").fetchall()
    ingestor().run()
    with database(settings.database_url) as connection:
        after = connection.execute("SELECT id,updated_at FROM sessions ORDER BY id").fetchall()
    assert before == after

    def no_scan(*args, **kwargs):
        raise AssertionError("unchanged corpus must not prepare episode inputs")

    monkeypatch.setattr(EpisodeBuilder, "_prepare_session_inputs", no_scan)
    assert EpisodeBuilder(settings).run().reused


def test_append_refreshes_only_affected_sessions(corpus, monkeypatch):
    import orjson

    settings, codex_path, _ = corpus

    def sync():
        return Ingestor(
            settings, [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)]
        ).run()

    sync()
    EpisodeBuilder(settings).run()
    with database(settings.database_url) as connection:
        untouched = connection.execute("SELECT updated_at FROM sessions WHERE provider='claude'").fetchone()[
            "updated_at"
        ]
        changed = int(connection.execute("SELECT id FROM sessions WHERE provider='codex'").fetchone()["id"])
    with codex_path.open("ab") as handle:
        handle.write(
            orjson.dumps(
                {
                    "timestamp": "2026-07-18T02:00:10Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Fixed the widget"}],
                    },
                }
            )
            + b"\n"
        )
    sync()
    observed = []
    prepare = EpisodeBuilder._prepare_session_inputs

    def bounded(connection, *, session_ids=None):
        observed.append(session_ids)
        return prepare(connection, session_ids=session_ids)

    monkeypatch.setattr(EpisodeBuilder, "_prepare_session_inputs", staticmethod(bounded))
    result = EpisodeBuilder(settings).run()
    assert observed == [[changed]]
    assert result.rebuilt_sessions == 1
    with database(settings.database_url) as connection:
        assert (
            connection.execute("SELECT updated_at FROM sessions WHERE provider='claude'").fetchone()[
                "updated_at"
            ]
            == untouched
        )


def test_checkpoint_preserves_changes_arriving_after_capture(corpus):
    from chatreview.source_changes import source_changes

    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)]).run()
    with database(settings.database_url) as connection:
        captured = source_changes(connection, "test_source_checkpoint")
        captured.record(connection)
        connection.commit()
        assert source_changes(connection, "test_source_checkpoint").session_ids == []
        # Simulate a writer committing after the captured snapshot.
        connection.execute("UPDATE source_revisions SET updated_at=clock_timestamp()")
        captured.record(connection)
        connection.commit()
        assert source_changes(connection, "test_source_checkpoint").session_ids
