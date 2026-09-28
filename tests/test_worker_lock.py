from __future__ import annotations

import os
import time
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from chatreview import worker
from chatreview.db import database


@dataclass
class _Summary:
    value: int = 1


def test_worker_keeps_lock_without_idle_transaction(monkeypatch) -> None:
    base_url = os.environ.get(
        "CHATREVIEW_TEST_DATABASE_URL", "postgresql:///chatreview?port=6543"
    )
    connection_options = conninfo_to_dict(base_url)
    connection_options["options"] = "-c idle_in_transaction_session_timeout=100ms"
    database_url = make_conninfo(**connection_options)
    lock_name = f"test-worker-{uuid4().hex}"
    monkeypatch.setattr(worker, "WORKER_LOCK", lock_name)
    monkeypatch.setattr(worker, "migrate", lambda _url: None)
    monkeypatch.setattr(
        worker, "EpisodeBuilder", lambda *_args, **_kwargs: SimpleNamespace(run=lambda: _Summary())
    )
    monkeypatch.setattr(
        worker,
        "automation_status",
        lambda _connection: {"refresh": {"needs_timesheet": False, "needs_token_costs": False}},
    )

    def sync_sources(*_args, **_kwargs):
        # The production server kills transactions idle for five minutes. A short
        # limit reproduces that failure without running a full archive pass.
        time.sleep(0.2)
        with (
            database(database_url) as challenger,
            challenger.try_advisory_lock(lock_name) as acquired,
        ):
            assert not acquired
        return _Summary()

    monkeypatch.setattr(worker, "sync_sources", sync_sources)
    settings = SimpleNamespace(database_url=database_url)
    result = worker.run_cycle(settings, summaries=False)
    assert result is not None
    assert result.sync == {"value": 1}
    with (
        database(database_url) as challenger,
        challenger.try_advisory_lock(lock_name) as acquired,
    ):
        assert acquired
