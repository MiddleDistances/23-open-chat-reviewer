from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

from chatreview.source_selection import (
    HistoryScope,
    preview_source_selection,
    select_sources,
)
from chatreview.types import SourceSpec


def _source(
    tmp_path: Path,
    relative: str,
    *,
    provider: str = "claude",
    source_kind: str = "session",
    mtime: datetime | None = None,
) -> SourceSpec:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"source")
    if mtime is not None:
        timestamp = mtime.replace(tzinfo=UTC).timestamp()
        os.utime(path, (timestamp, timestamp))
    return SourceSpec(provider, path, source_kind)


def test_codex_session_date_path_is_an_exact_scope_boundary(tmp_path: Path) -> None:
    old = _source(
        tmp_path,
        "codex/sessions/2026/07/17/rollout-old.jsonl",
        provider="codex",
    )
    selected = _source(
        tmp_path,
        "codex/sessions/2026/07/18/rollout-selected.jsonl",
        provider="codex",
    )
    future = _source(
        tmp_path,
        "codex/sessions/2026/07/19/rollout-future.jsonl",
        provider="codex",
    )

    assert select_sources(
        [old, selected, future],
        since=date(2026, 7, 18),
        until=date(2026, 7, 18),
    ) == [selected]


def test_aggregate_history_is_retained_and_reported(tmp_path: Path) -> None:
    history = _source(
        tmp_path,
        "claude/history.jsonl",
        source_kind="history",
        mtime=datetime(2026, 7, 1),
    )
    preview = preview_source_selection(
        [history], since=date(2026, 7, 18), until=date(2026, 7, 18)
    )

    assert preview.included_sources == (history,)
    assert preview.aggregate_files == 1
    assert preview.aggregate_paths == (str(history.path),)
    assert preview.excluded_files == 0


def test_unknown_source_uses_its_mtime_as_a_conservative_file_bound(tmp_path: Path) -> None:
    old = _source(tmp_path, "claude/projects/old.jsonl", mtime=datetime(2026, 7, 17, 23, 59))
    selected = _source(
        tmp_path,
        "claude/projects/selected.jsonl",
        mtime=datetime(2026, 7, 18, 12),
    )
    future = _source(tmp_path, "claude/projects/future.jsonl", mtime=datetime(2026, 7, 19))

    preview = preview_source_selection(
        [old, selected, future], since=date(2026, 7, 18), until=date(2026, 7, 18)
    )

    assert preview.included_sources == (selected,)
    assert preview.mtime_bound_files == 3
    assert preview.excluded_files == 2
    assert preview.excluded_paths == (str(future.path), str(old.path))


def test_git_sources_are_not_dropped_by_conversation_history_scope(tmp_path: Path) -> None:
    git = _source(
        tmp_path,
        "git-sources/repository.jsonl",
        provider="git",
        source_kind="repository",
        mtime=datetime(2026, 8, 30),
    )

    preview = preview_source_selection([git], since=date(2020, 1, 1), until=date(2020, 1, 2))

    assert preview.included_sources == (git,)
    assert preview.unbounded_files == 1
    assert preview.unbounded_paths == (str(git.path),)


def test_scope_rejects_reversed_dates() -> None:
    try:
        HistoryScope(date(2026, 7, 19), date(2026, 7, 18))
    except ValueError as exc:
        assert "history-until" in str(exc)
    else:
        raise AssertionError("reversed history scope was accepted")
