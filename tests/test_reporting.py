from __future__ import annotations

from chatreview.db import database
from chatreview.episodes import EpisodeBuilder
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.reporting import build_baseline_report


def test_baseline_report_contains_grounded_review_surfaces(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    EpisodeBuilder(settings).run()
    with database(settings.database_url, read_only=True) as connection:
        report = build_baseline_report(connection, top=10, min_sessions=1)
    assert "# Chat Corpus Baseline Review" in report
    assert "Repeated normalized error signatures" in report
    assert "frobnicator" in report
    assert "Largest sessions" in report
    assert "blind-spot" in report
