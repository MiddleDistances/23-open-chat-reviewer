"""Deterministic, read-only selection of source files for an initial archive sync.

The archive scope is intentionally a source-level decision.  Codex session paths carry
an exact ``sessions/YYYY/MM/DD`` date, so those files can be selected without opening
them.  Other conversation files are not safely splittable at discovery time; their UTC
file modification day is used as a coarse bound.  Provider aggregate history files are
always retained and reported because excluding them could silently drop records from the
requested interval.  Git evidence is similarly retained because ``--history-since``
scopes conversation history, not repository metadata.

This module never opens or edits a source file's contents.  ``preview_source_selection``
only calls ``Path.stat`` to report bytes and to apply the documented mtime fallback.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from chatreview.types import SourceSpec

SelectionKind = Literal["exact", "mtime", "aggregate", "unbounded"]
DateLike = date | datetime | str | None
StatFunction = Callable[[Path], os.stat_result]


@dataclass(frozen=True, slots=True)
class HistoryScope:
    """Inclusive UTC calendar-day bounds for the initial conversation archive."""

    since: date | None = None
    until: date | None = None

    def __post_init__(self) -> None:
        since = coerce_scope_date(self.since, option="history-since")
        until = coerce_scope_date(self.until, option="history-until")
        if since is not None and until is not None and since > until:
            raise ValueError("history-until must be on or after history-since")
        object.__setattr__(self, "since", since)
        object.__setattr__(self, "until", until)

    @property
    def active(self) -> bool:
        """Whether at least one date bound was supplied."""

        return self.since is not None or self.until is not None

    def contains(self, value: date) -> bool:
        """Return whether an inclusive date belongs to this scope."""

        if self.since is not None and value < self.since:
            return False
        if self.until is not None and value > self.until:
            return False
        return True

    def as_dict(self) -> dict[str, str | None]:
        return {
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
        }


@dataclass(frozen=True, slots=True)
class SourceSelectionDecision:
    """The auditable decision made for one discovered source."""

    source: SourceSpec
    included: bool
    kind: SelectionKind
    reason: str
    exact_date: date | None = None
    mtime: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.source.provider,
            "source_kind": self.source.source_kind,
            "path": str(self.source.path),
            "included": self.included,
            "kind": self.kind,
            "reason": self.reason,
            "exact_date": self.exact_date.isoformat() if self.exact_date else None,
            "mtime": self.mtime.isoformat().replace("+00:00", "Z") if self.mtime else None,
        }


@dataclass(frozen=True, slots=True)
class SourceSelectionPreview:
    """Counts and decisions for a source scope preview.

    ``included_sources`` and ``excluded_sources`` are sorted tuples so the result is
    stable across providers and worker processes.  The byte counts are filesystem
    observations, not estimates of the eventual PostgreSQL footprint.
    """

    scope: HistoryScope
    included_sources: tuple[SourceSpec, ...]
    excluded_sources: tuple[SourceSpec, ...]
    decisions: tuple[SourceSelectionDecision, ...]
    included_bytes: int = 0
    excluded_bytes: int = 0
    exact_files: int = 0
    mtime_bound_files: int = 0
    aggregate_files: int = 0
    unbounded_files: int = 0
    missing_files: int = 0

    @property
    def total_files(self) -> int:
        return len(self.decisions)

    @property
    def excluded_files(self) -> int:
        return len(self.excluded_sources)

    @property
    def selected_files(self) -> int:
        return len(self.included_sources)

    @property
    def exact_paths(self) -> tuple[str, ...]:
        return tuple(str(item.source.path) for item in self.decisions if item.kind == "exact")

    @property
    def mtime_bound_paths(self) -> tuple[str, ...]:
        return tuple(str(item.source.path) for item in self.decisions if item.kind == "mtime")

    @property
    def aggregate_paths(self) -> tuple[str, ...]:
        return tuple(str(item.source.path) for item in self.decisions if item.kind == "aggregate")

    @property
    def unbounded_paths(self) -> tuple[str, ...]:
        return tuple(str(item.source.path) for item in self.decisions if item.kind == "unbounded")

    @property
    def excluded_paths(self) -> tuple[str, ...]:
        return tuple(str(source.path) for source in self.excluded_sources)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-compatible preview data for setup/API consumers."""

        return {
            "scope": self.scope.as_dict(),
            "total_files": self.total_files,
            "selected_files": self.selected_files,
            "excluded_files": self.excluded_files,
            "included_bytes": self.included_bytes,
            "excluded_bytes": self.excluded_bytes,
            "exact_files": self.exact_files,
            "mtime_bound_files": self.mtime_bound_files,
            "aggregate_files": self.aggregate_files,
            "unbounded_files": self.unbounded_files,
            "missing_files": self.missing_files,
            "decisions": [decision.as_dict() for decision in self.decisions],
        }


def coerce_scope_date(value: DateLike, *, option: str) -> date | None:
    """Parse a CLI/API date value and raise a useful option-specific error."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{option} must use YYYY-MM-DD") from exc
    raise TypeError(f"{option} must be a date or YYYY-MM-DD string")


def codex_session_date(source: SourceSpec) -> date | None:
    """Return the exact date encoded by a Codex ``sessions/YYYY/MM/DD`` path."""

    if source.provider != "codex" or source.source_kind not in {
        "session",
        "subagent",
        "workflow-journal",
    }:
        return None
    parts = source.path.parts
    for index, part in enumerate(parts):
        if part != "sessions" or index + 3 >= len(parts):
            continue
        year, month, day = parts[index + 1 : index + 4]
        if not (year.isdecimal() and month.isdecimal() and day.isdecimal()):
            continue
        if len(year) != 4 or len(month) != 2 or len(day) != 2:
            continue
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            continue
    return None


def preview_source_selection(
    sources: Iterable[SourceSpec],
    *,
    since: DateLike = None,
    until: DateLike = None,
    scope: HistoryScope | None = None,
    stat_fn: StatFunction | None = None,
) -> SourceSelectionPreview:
    """Preview which discovered sources belong to an inclusive history scope.

    The helper is intentionally independent of PostgreSQL and suitable for setup
    screens.  When a scope is active, aggregate conversation sources are included even
    if their mtime is outside the range.  Sources without an exact Codex path date use
    their UTC mtime calendar day as a coarse, documented fallback.  Missing files are
    retained as ``unbounded`` so a concurrent source removal cannot change the selected
    set into a silent data loss.
    """

    if scope is not None and (since is not None or until is not None):
        raise ValueError("pass either scope or since/until, not both")
    selected_scope = scope or HistoryScope(since, until)
    stat = stat_fn or _path_stat
    decisions: list[SourceSelectionDecision] = []
    included: list[SourceSpec] = []
    excluded: list[SourceSpec] = []
    included_bytes = 0
    excluded_bytes = 0
    exact_files = 0
    mtime_bound_files = 0
    aggregate_files = 0
    unbounded_files = 0
    missing_files = 0

    ordered_sources = sorted(
        sources,
        key=lambda item: (item.provider, item.source_kind, str(item.path)),
    )
    for source in ordered_sources:
        size, mtime = _file_observation(source.path, stat)
        exact_date = codex_session_date(source)
        kind: SelectionKind
        reason: str
        include = True

        if not selected_scope.active:
            kind = "unbounded"
            reason = "no history scope requested"
        elif source.provider == "git":
            kind = "unbounded"
            reason = "Git metadata is outside conversation history scope"
        elif source.source_kind == "history":
            kind = "aggregate"
            reason = "aggregate history cannot be safely split at discovery"
        elif exact_date is not None:
            kind = "exact"
            include = selected_scope.contains(exact_date)
            reason = (
                "Codex session date is inside history scope"
                if include
                else "Codex session date is outside history scope"
            )
            exact_files += 1
        elif mtime is None:
            kind = "unbounded"
            reason = "source mtime unavailable; retained conservatively"
            missing_files += 1
        else:
            kind = "mtime"
            mtime_date = mtime.date()
            include = selected_scope.contains(mtime_date)
            reason = (
                "UTC source mtime day is inside history scope"
                if include
                else "UTC source mtime day is outside history scope"
            )
            mtime_bound_files += 1

        decision = SourceSelectionDecision(
            source=source,
            included=include,
            kind=kind,
            reason=reason,
            exact_date=exact_date,
            mtime=mtime,
        )
        decisions.append(decision)
        if include:
            included.append(source)
            included_bytes += size
        else:
            excluded.append(source)
            excluded_bytes += size
        if kind == "aggregate":
            aggregate_files += 1
        if kind == "unbounded":
            unbounded_files += 1

    return SourceSelectionPreview(
        scope=selected_scope,
        included_sources=tuple(included),
        excluded_sources=tuple(excluded),
        decisions=tuple(decisions),
        included_bytes=included_bytes,
        excluded_bytes=excluded_bytes,
        exact_files=exact_files,
        mtime_bound_files=mtime_bound_files,
        aggregate_files=aggregate_files,
        unbounded_files=unbounded_files,
        missing_files=missing_files,
    )


def select_sources(
    sources: Iterable[SourceSpec],
    *,
    since: DateLike = None,
    until: DateLike = None,
    scope: HistoryScope | None = None,
    stat_fn: StatFunction | None = None,
) -> list[SourceSpec]:
    """Return the deterministic, read-only source subset for a history scope."""

    return list(
        preview_source_selection(
            sources,
            since=since,
            until=until,
            scope=scope,
            stat_fn=stat_fn,
        ).included_sources
    )


def _path_stat(path: Path) -> os.stat_result:
    return path.stat()


def _file_observation(path: Path, stat_fn: StatFunction) -> tuple[int, datetime | None]:
    try:
        observed = stat_fn(path)
    except OSError:
        return 0, None
    return observed.st_size, datetime.fromtimestamp(observed.st_mtime, tz=UTC)


__all__ = [
    "HistoryScope",
    "SourceSelectionDecision",
    "SourceSelectionPreview",
    "codex_session_date",
    "coerce_scope_date",
    "preview_source_selection",
    "select_sources",
]
