"""Repeatable sync worker for chats, Git activity, and derived review views."""

from __future__ import annotations

import os
import signal
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from chatreview.automation import automation_status
from chatreview.config import Settings
from chatreview.db import database, migrate
from chatreview.episodes import EpisodeBuilder
from chatreview.ingest import sync_sources
from chatreview.resume import ProviderResumeModel, ResumeSurfaceRefresher
from chatreview.summary_providers import provider_from_environment
from chatreview.timesheets import build_timesheet

WORKER_LOCK = "open-chat-reviewer:worker-cycle"


@dataclass(frozen=True, slots=True)
class WorkerCycleResult:
    """Serializable result from one complete worker cycle."""

    started_at: str
    completed_at: str
    sync: dict[str, Any]
    episodes: dict[str, Any]
    timesheet: dict[str, Any] | None
    summaries: dict[str, Any] | None


def run_cycle(
    settings: Settings,
    *,
    providers: set[str] | None = None,
    sync_workers: int = 1,
    summaries: bool | None = None,
    summary_hours: int = 24,
    progress: Callable[[str], None] | None = None,
) -> WorkerCycleResult | None:
    """Run one lock-protected sync and refresh cycle.

    Returns ``None`` when another worker owns the cycle lock. Source ingestion remains
    resumable and source directories remain read-only.
    """

    report = progress or (lambda _message: None)
    started = datetime.now(UTC)
    migrate(settings.database_url)
    with (
        database(settings.database_url) as lock_connection,
        lock_connection.try_advisory_lock(WORKER_LOCK) as acquired,
    ):
        if not acquired:
            report("another worker cycle is already active; skipping")
            return None
        sync = sync_sources(
            settings,
            providers=providers,
            workers=sync_workers,
            progress=report,
        )
        episode_summary = EpisodeBuilder(settings, progress=report).run()

        timesheet_summary = None
        with database(settings.database_url, read_only=True) as connection:
            status = automation_status(connection)
        if status["refresh"]["needs_timesheet"]:
            with database(settings.database_url) as connection:
                timesheet_summary = build_timesheet(connection, cutoff=datetime.now(UTC))

        if summaries is None:
            summaries = _env_bool("CHATREVIEW_ENABLE_SUMMARIES", default=False)
        resume_summary = None
        if summaries:
            provider = provider_from_environment()
            resume_summary = ResumeSurfaceRefresher(
                settings.database_url,
                ProviderResumeModel(provider),
                progress=report,
            ).run(hours=summary_hours)

    completed = datetime.now(UTC)
    return WorkerCycleResult(
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        sync=asdict(sync),
        episodes=asdict(episode_summary),
        timesheet=asdict(timesheet_summary) if timesheet_summary else None,
        summaries=asdict(resume_summary) if resume_summary else None,
    )


def run_forever(
    settings: Settings,
    *,
    interval_seconds: int = 21_600,
    providers: set[str] | None = None,
    sync_workers: int = 1,
    summaries: bool | None = None,
    summary_hours: int = 24,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Run cycles until SIGINT or SIGTERM, waiting between cycle start times."""

    interval_seconds = max(60, int(interval_seconds))
    report = progress or print
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    previous = {
        signal_number: signal.getsignal(signal_number)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    }
    for signal_number in previous:
        signal.signal(signal_number, stop)
    try:
        while not stopped.is_set():
            cycle_started = datetime.now(UTC)
            run_cycle(
                settings,
                providers=providers,
                sync_workers=sync_workers,
                summaries=summaries,
                summary_hours=summary_hours,
                progress=report,
            )
            elapsed = (datetime.now(UTC) - cycle_started).total_seconds()
            wait_seconds = max(1, interval_seconds - int(elapsed))
            report(f"next worker cycle in {wait_seconds} seconds")
            stopped.wait(wait_seconds)
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
