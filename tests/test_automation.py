from __future__ import annotations

from datetime import UTC, datetime

from chatreview.automation import automation_status
from chatreview.db import database
from chatreview.episodes import EpisodeBuilder
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.timesheets import build_timesheet


def test_automation_status_separates_freshness_from_review_readiness(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()

    with database(settings.database_url, read_only=True) as connection:
        before = automation_status(connection)

    assert before["refresh"]["needs_episodes"] is True
    assert before["refresh"]["needs_timesheet"] is True
    assert before["activities"]["total"] == 0
    assert not any("activity catalog" in warning for warning in before["warnings"])

    EpisodeBuilder(settings).run()
    with database(settings.database_url) as connection:
        build_timesheet(connection, cutoff=datetime(2026, 7, 19, tzinfo=UTC))
    with database(settings.database_url, read_only=True) as connection:
        after = automation_status(connection)

    assert after["episodes"]["fresh"] is True
    assert after["timesheet"]["fresh"] is True
    assert after["refresh"]["needs_episodes"] is False
    assert after["refresh"]["needs_timesheet"] is False
    assert after["status"] == "healthy"
