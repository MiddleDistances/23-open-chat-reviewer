from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

import chatreview.cli as cli
from chatreview.cli import app
from chatreview.ingest import Ingestor, IngestSummary
from chatreview.providers import ClaudeAdapter, CodexAdapter


def test_transient_retry_reloads_the_durable_source_snapshot(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    ingestor = Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    )
    source = ingestor.discover()[0]
    source_key = (source.provider, source.source_kind, str(source.path))
    durable_snapshot = {"source_id": 1, "revision_id": 1, "status": "failed"}
    snapshot_calls = 0
    observed_snapshots = []

    def load_snapshots(_connection):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return {} if snapshot_calls == 1 else {source_key: durable_snapshot}

    def ingest_source(_connection, _source, _adapter, *, force, source_row):
        observed_snapshots.append(source_row)
        retryable = len(observed_snapshots) == 1
        return {
            "processed": not retryable,
            "skipped": False,
            "reparsed": False,
            "events": 0,
            "text_units": 0,
            "artifacts": 0,
            "parse_errors": 0,
            "bytes_read": 0,
            "retryable": retryable,
        }

    monkeypatch.setattr(ingestor, "discover", lambda *, providers=None: [source])
    monkeypatch.setattr(ingestor, "_load_source_snapshots", load_snapshots)
    monkeypatch.setattr(ingestor, "_ingest_source", ingest_source)
    monkeypatch.setattr(ingestor, "_finalize", lambda _connection: None)

    summary = ingestor.run()

    assert summary.processed_files == 1
    assert snapshot_calls == 2
    assert observed_snapshots == [None, durable_snapshot]


def test_sync_workers_ingest_each_source_once(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("CHATREVIEW_MACHINE_ID", str(settings.machine_id))
    monkeypatch.setenv("CHATREVIEW_MACHINE_NAME", settings.machine_name)
    monkeypatch.setenv("CHATREVIEW_CONTRIBUTOR", settings.contributor or "")
    args = [
        "sync",
        "--data-dir",
        str(settings.data_dir),
        "--codex-root",
        str(settings.codex_root),
        "--claude-root",
        str(settings.claude_root),
        "--gemini-root",
        str(settings.gemini_root),
        "--git-root",
        str(settings.git_root),
        "--workers",
        "2",
        "--progress-every",
        "1",
    ]
    runner = CliRunner()
    pool_closes: list[bool] = []
    monkeypatch.setattr(cli, "close_pools", lambda: pool_closes.append(True), raising=False)

    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert pool_closes == [True]
    assert "4 processed, 0 unchanged" in first.output
    assert "10 events" in first.output

    second = runner.invoke(app, args)
    assert second.exit_code == 0, second.output
    assert "0 processed, 4 unchanged" in second.output
    assert "0 events" in second.output


def test_sync_explains_gemini_export_fallback_when_no_documents(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("CHATREVIEW_MACHINE_ID", str(settings.machine_id))
    monkeypatch.setenv("CHATREVIEW_MACHINE_NAME", settings.machine_name)
    monkeypatch.setenv("CHATREVIEW_CONTRIBUTOR", settings.contributor or "")

    result = CliRunner().invoke(
        app,
        [
            "sync",
            "--data-dir",
            str(settings.data_dir),
            "--codex-root",
            str(settings.codex_root),
            "--claude-root",
            str(settings.claude_root),
            "--gemini-root",
            str(settings.gemini_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "export or supported API source is required" in result.output


def test_sync_cli_passes_history_scope_and_reports_aggregate_sources(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("CHATREVIEW_MACHINE_ID", str(settings.machine_id))
    monkeypatch.setenv("CHATREVIEW_MACHINE_NAME", settings.machine_name)
    observed: dict[str, object] = {}

    def fake_sync(_settings, **kwargs):
        observed.update(kwargs)
        return IngestSummary(
            processed_files=3,
            aggregate_files=2,
            excluded_files=1,
            mtime_bound_files=1,
        )

    monkeypatch.setattr(cli, "sync_sources", fake_sync)
    result = CliRunner().invoke(
        app,
        [
            "sync",
            "--data-dir",
            str(settings.data_dir),
            "--codex-root",
            str(settings.codex_root),
            "--claude-root",
            str(settings.claude_root),
            "--gemini-root",
            str(settings.gemini_root),
            "--no-git",
            "--history-since",
            "2026-07-18",
            "--history-until",
            "2026-07-19",
        ],
    )

    assert result.exit_code == 0, result.output
    assert observed["history_since"] == date(2026, 7, 18)
    assert observed["history_until"] == date(2026, 7, 19)
    assert "1 sources excluded before persistence" in result.output
    assert "2 aggregate history files retained" in result.output


def test_sync_cli_rejects_reversed_history_scope(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("CHATREVIEW_MACHINE_ID", str(settings.machine_id))
    monkeypatch.setattr(cli, "sync_sources", lambda *_args, **_kwargs: None)
    result = CliRunner().invoke(
        app,
        [
            "sync",
            "--data-dir",
            str(settings.data_dir),
            "--codex-root",
            str(settings.codex_root),
            "--claude-root",
            str(settings.claude_root),
            "--history-since",
            "2026-07-19",
            "--history-until",
            "2026-07-18",
        ],
    )

    assert result.exit_code != 0
    assert "history-until must be on or after history-since" in result.output
