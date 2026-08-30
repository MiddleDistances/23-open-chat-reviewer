from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from chatreview.db import Session
from chatreview.providers.base import stable_hash
from chatreview.semantic import corpus_revision

ALGORITHM_VERSION = 3
INACTIVITY_GAP = timedelta(hours=1)


@dataclass(slots=True)
class EventPoint:
    event_id: int
    session_id: int
    root_session_id: int
    contributor_key: str
    contributor_id: int | None
    project_id: int | None
    timestamp: datetime
    direct_user: bool


@dataclass(slots=True)
class Segment:
    contributor_key: str
    contributor_id: int | None
    project_id: int | None
    start: datetime
    end: datetime
    event_ids: set[int] = field(default_factory=set)
    user_times: list[datetime] = field(default_factory=list)
    event_times: dict[int, datetime] = field(default_factory=dict)


@dataclass(slots=True)
class Slice:
    contributor_key: str
    contributor_id: int | None
    project_id: int | None
    start: datetime
    end: datetime
    ambiguous: bool
    reason: str | None
    event_ids: set[int]


@dataclass(frozen=True, slots=True)
class TimesheetBuildSummary:
    snapshot_id: int
    snapshot_key: str
    intervals: int
    total_seconds: int
    ambiguity_count: int
    corpus_fingerprint: str
    cutoff: datetime
    reused: bool = False


@dataclass(frozen=True, slots=True)
class TimesheetFilters:
    date_from: date | None = None
    date_to: date | None = None
    contributor: str | None = None
    project: str | None = None
    projects: tuple[str, ...] = ()
    activity: str | None = None
    classification: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    content: bytes
    manifest: dict[str, Any]


def build_timesheet(
    connection: Session,
    *,
    cutoff: datetime | None = None,
    timezone_name: str | None = None,
    force: bool = False,
) -> TimesheetBuildSummary:
    """Build one complete, versioned interval snapshot from canonical event evidence."""

    cutoff = _utc(cutoff or datetime.now(UTC))
    zone = _local_zone(timezone_name)
    zone_name = zone.key
    fingerprint = corpus_revision(connection)
    snapshot_key = stable_hash(
        f"timesheet\0{ALGORITHM_VERSION}\0{fingerprint}\0{cutoff.isoformat()}\0{zone_name}"
    )
    existing = connection.execute(
        "SELECT * FROM timesheet_snapshots WHERE snapshot_key=?", (snapshot_key,)
    ).fetchone()
    if existing is not None and existing["status"] == "complete" and not force:
        return _summary(existing, reused=True)
    if existing is None:
        snapshot = connection.execute(
            """
            INSERT INTO timesheet_snapshots(
                snapshot_key, corpus_fingerprint, cutoff, algorithm_version, timezone, status
            ) VALUES (?, ?, ?, ?, ?, 'building') RETURNING id
            """,
            (snapshot_key, fingerprint, cutoff, ALGORITHM_VERSION, zone_name),
        ).fetchone()
        assert snapshot is not None
        snapshot_id = int(snapshot["id"])
    else:
        snapshot_id = int(existing["id"])
        connection.execute("DELETE FROM work_intervals WHERE snapshot_id=?", (snapshot_id,))
        connection.execute(
            """
            UPDATE timesheet_snapshots SET status='building', error=NULL,
                generated_at=clock_timestamp(), completed_at=NULL,
                ambiguity_count=0, interval_count=0, total_seconds=0
            WHERE id=?
            """,
            (snapshot_id,),
        )
    connection.commit()

    try:
        points = _event_points(connection, cutoff)
        segments = _segments(points)
        unallocated_id = _unallocated_project(connection)
        slices = _allocate_slices(segments, unallocated_id=unallocated_id)
        slices = _split_local_midnights(slices, zone=zone)
        intervals = _persist_intervals(connection, snapshot_id, slices, zone=zone)
        total_seconds = sum(item["seconds"] for item in intervals)
        ambiguity_count = sum(item["ambiguous"] for item in intervals)
        connection.execute(
            """
            UPDATE timesheet_snapshots SET status='complete', completed_at=clock_timestamp(),
                interval_count=?, total_seconds=?, ambiguity_count=?
            WHERE id=?
            """,
            (len(intervals), total_seconds, ambiguity_count, snapshot_id),
        )
        connection.commit()
    except BaseException as exc:
        connection.rollback()
        connection.execute(
            "UPDATE timesheet_snapshots SET status='failed', error=? WHERE id=?",
            (f"{type(exc).__name__}: {exc}", snapshot_id),
        )
        connection.commit()
        raise
    row = connection.execute("SELECT * FROM timesheet_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    assert row is not None
    return _summary(row)


def latest_snapshot(connection: Session) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT * FROM timesheet_snapshots
        WHERE status='complete' ORDER BY completed_at DESC, id DESC LIMIT 1
        """
    ).fetchone()
    return dict(row) if row is not None else None


def timesheet_calendar(
    connection: Session,
    *,
    financial_year: str | None = None,
    year: int | None = None,
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate the latest calculated intervals by financial-year day and project."""

    snapshot_row = (
        connection.execute(
            "SELECT * FROM timesheet_snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone()
        if snapshot_id is not None
        else None
    )
    snapshot = (
        dict(snapshot_row)
        if snapshot_row is not None
        else None if snapshot_id is not None else latest_snapshot(connection)
    )
    if snapshot is None or snapshot["status"] != "complete":
        return {
            "snapshot": None,
            "financial_year": financial_year,
            "available_financial_years": [],
            "year": year,
            "available_years": [],
            "days": [],
            "projects": [],
        }

    available_start_years = [
        int(row["start_year"])
        for row in connection.execute(
            """
            SELECT DISTINCT (
                EXTRACT(YEAR FROM local_date)::integer
                - CASE WHEN EXTRACT(MONTH FROM local_date)<7 THEN 1 ELSE 0 END
            ) AS start_year
            FROM work_intervals
            WHERE snapshot_id=?
            ORDER BY start_year DESC
            """,
            (snapshot["id"],),
        ).fetchall()
    ]
    available_financial_years = [_financial_year_label(year) for year in available_start_years]
    available_years = sorted(
        {
            int(row["year"])
            for row in connection.execute(
                """
                SELECT DISTINCT EXTRACT(YEAR FROM local_date)::integer AS year
                FROM work_intervals WHERE snapshot_id=?
                """,
                (snapshot["id"],),
            ).fetchall()
        },
        reverse=True,
    )
    if year is not None:
        selected_financial_year = financial_year
        date_from, date_to = date(year, 1, 1), date(year, 12, 31)
    else:
        zone = _local_zone(str(snapshot["timezone"]))
        cutoff_date = _utc(snapshot["cutoff"]).astimezone(zone).date()
        selected_financial_year = financial_year or _financial_year_for_date(cutoff_date)
        date_from, date_to = financial_year_dates(selected_financial_year)
    zone = _local_zone(str(snapshot["timezone"]))
    period_start = datetime.combine(date_from, time.min, zone).astimezone(UTC)
    period_end = datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(UTC)
    evidence_profiles: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        """
        WITH calendar_projects AS (
            SELECT DISTINCT project_id
            FROM work_intervals
            WHERE snapshot_id=? AND local_date>=? AND local_date<=?
        )
        SELECT DISTINCT project.project_key, session.provider,
               machine.id AS machine_id, machine.name AS machine_name
        FROM calendar_projects calendar
        JOIN projects project ON project.id=calendar.project_id
        JOIN sessions session ON session.project_id=calendar.project_id
        JOIN machines machine ON machine.id=session.machine_id
        WHERE session.started_at<?
          AND COALESCE(session.ended_at, session.started_at)>=?
        ORDER BY project.project_key, session.provider, machine.name, machine.id
        """,
        (snapshot["id"], date_from, date_to, period_end, period_start),
    ).fetchall():
        profile = evidence_profiles.setdefault(
            str(row["project_key"]),
            {"providers": set(), "machines": {}},
        )
        profile["providers"].add(str(row["provider"]))
        profile["machines"][str(row["machine_id"])] = str(row["machine_name"])
    rows = connection.execute(
        """
        WITH calendar_intervals AS MATERIALIZED (
            SELECT *
            FROM work_intervals
            WHERE snapshot_id=?
              AND local_date>=?
              AND local_date<=?
        ),
        interval_sources AS (
            SELECT interval_evidence.interval_id,
                   BOOL_OR(session.provider='git') AS has_git,
                   BOOL_OR(session.provider<>'git') AS has_chat
            FROM work_interval_evidence interval_evidence
            JOIN calendar_intervals target ON target.id=interval_evidence.interval_id
            JOIN events event ON event.id=interval_evidence.event_id
            JOIN sessions session ON session.id=event.session_id
            GROUP BY interval_evidence.interval_id
        )
        SELECT interval.local_date,
               project.id AS project_id,
               COALESCE(project.project_key, 'unallocated') AS project_key,
               COALESCE(project.name, 'Unallocated') AS project,
               SUM(interval.exact_seconds)::bigint AS exact_seconds,
               COUNT(*)::bigint AS interval_count,
               SUM(interval.evidence_count)::bigint AS evidence_count,
               COALESCE(BOOL_OR(interval_sources.has_git), false) AS has_git,
               COALESCE(BOOL_OR(interval_sources.has_chat), false) AS has_chat,
               COALESCE(SUM(
                   CASE WHEN interval.ambiguous THEN interval.exact_seconds ELSE 0 END
               ), 0)::bigint AS ambiguous_seconds
        FROM calendar_intervals interval
        LEFT JOIN projects project ON project.id=interval.project_id
        LEFT JOIN interval_sources ON interval_sources.interval_id=interval.id
        GROUP BY interval.local_date, project.id, project.project_key, project.name
        ORDER BY interval.local_date, exact_seconds DESC, project.name
        """,
        (snapshot["id"], date_from, date_to),
    ).fetchall()

    days: dict[date, dict[str, Any]] = {}
    projects: dict[str, dict[str, Any]] = {}
    for row in rows:
        local_date = row["local_date"]
        project_key = str(row["project_key"])
        seconds = int(row["exact_seconds"] or 0)
        intervals = int(row["interval_count"] or 0)
        evidence = int(row["evidence_count"] or 0)
        ambiguous = int(row["ambiguous_seconds"] or 0)
        evidence_kinds = [
            kind
            for kind, present in (
                ("git", bool(row["has_git"])),
                ("chat", bool(row["has_chat"])),
            )
            if present
        ]
        project_item = {
            "project_id": int(row["project_id"]) if row["project_id"] is not None else None,
            "project_key": project_key,
            "project": str(row["project"]),
            "exact_seconds": seconds,
            "interval_count": intervals,
            "evidence_count": evidence,
            "evidence_kinds": evidence_kinds,
            "ambiguous_seconds": ambiguous,
        }
        day = days.setdefault(
            local_date,
            {
                "date": local_date.isoformat(),
                "exact_seconds": 0,
                "interval_count": 0,
                "evidence_count": 0,
                "ambiguous_seconds": 0,
                "evidence_kinds": [],
                "projects": [],
            },
        )
        day["exact_seconds"] += seconds
        day["interval_count"] += intervals
        day["evidence_count"] += evidence
        day["ambiguous_seconds"] += ambiguous
        for kind in evidence_kinds:
            if kind not in day["evidence_kinds"]:
                day["evidence_kinds"].append(kind)
        day["projects"].append(project_item)

        project = projects.setdefault(
            project_key,
            {
                "project_id": project_item["project_id"],
                "project_key": project_key,
                "project": project_item["project"],
                "exact_seconds": 0,
                "interval_count": 0,
                "evidence_count": 0,
                "ambiguous_seconds": 0,
                "evidence_kinds": [],
                "active_days": 0,
                "first_date": local_date.isoformat(),
                "last_date": local_date.isoformat(),
            },
        )
        project["exact_seconds"] += seconds
        project["interval_count"] += intervals
        project["evidence_count"] += evidence
        project["ambiguous_seconds"] += ambiguous
        for kind in evidence_kinds:
            if kind not in project["evidence_kinds"]:
                project["evidence_kinds"].append(kind)
        project["active_days"] += 1
        project["first_date"] = min(project["first_date"], local_date.isoformat())
        project["last_date"] = max(project["last_date"], local_date.isoformat())

    for project_key, project in projects.items():
        profile = evidence_profiles.get(project_key, {"providers": set(), "machines": {}})
        providers = sorted(profile["providers"])
        project["providers"] = providers
        project["machines"] = [
            {"machine_id": machine_id, "machine_name": machine_name}
            for machine_id, machine_name in sorted(
                profile["machines"].items(),
                key=lambda item: (item[1].casefold(), item[0]),
            )
        ]

    return {
        "snapshot": snapshot,
        "financial_year": selected_financial_year,
        "available_financial_years": available_financial_years,
        "year": year,
        "available_years": available_years,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "days": list(days.values()),
        "projects": sorted(
            projects.values(),
            key=lambda item: (-item["exact_seconds"], item["project"].casefold()),
        ),
    }


def compute_combined_timesheet(
    connection: Session,
    *,
    financial_year: str,
    project_keys: tuple[str, ...] = (),
    snapshot_id: int | None = None,
) -> dict[str, Any]:
    """Union selected repository clocks per contributor and Perth calendar day."""

    snapshot_row = (
        connection.execute(
            "SELECT * FROM timesheet_snapshots WHERE id=? AND status='complete'",
            (snapshot_id,),
        ).fetchone()
        if snapshot_id is not None
        else None
    )
    if snapshot_id is not None and snapshot_row is None:
        raise ValueError(f"timesheet snapshot {snapshot_id} is not available")
    snapshot = dict(snapshot_row) if snapshot_row is not None else latest_snapshot(connection)
    if snapshot is None:
        raise ValueError("no complete timesheet snapshot is available")
    date_from, date_to = financial_year_dates(financial_year)
    selected_keys = tuple(dict.fromkeys(project_keys))
    selected_projects: list[dict[str, Any]] = []
    if selected_keys:
        selected_projects = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, project_key, name AS project
                FROM projects WHERE project_key=ANY(?)
                """,
                (list(selected_keys),),
            ).fetchall()
        ]
        by_key = {str(project["project_key"]): project for project in selected_projects}
        missing = [project_key for project_key in selected_keys if project_key not in by_key]
        if missing:
            raise ValueError(f"unknown project keys: {', '.join(missing)}")
        selected_projects = [by_key[project_key] for project_key in selected_keys]

    clauses = [
        "interval.snapshot_id=?",
        "interval.local_date>=?",
        "interval.local_date<=?",
        "interval.project_id IS NOT NULL",
    ]
    parameters: list[Any] = [int(snapshot["id"]), date_from, date_to]
    if selected_keys:
        clauses.append("project.project_key=ANY(?)")
        parameters.append(list(selected_keys))
    rows = connection.execute(
        f"""
        SELECT interval.id, interval.contributor_id, interval.local_date,
               interval.started_at, interval.ended_at, interval.exact_seconds,
               interval.ambiguous, interval.evidence_count,
               contributor.display_name AS contributor,
               project.project_key, project.name AS project
        FROM work_intervals interval
        LEFT JOIN contributors contributor ON contributor.id=interval.contributor_id
        JOIN projects project ON project.id=interval.project_id
        WHERE {' AND '.join(clauses)}
        ORDER BY interval.local_date, interval.contributor_id NULLS LAST,
                 interval.started_at, interval.ended_at, interval.id
        """,
        parameters,
    ).fetchall()
    if not selected_keys:
        catalog: dict[str, dict[str, Any]] = {}
        for row in rows:
            catalog.setdefault(
                str(row["project_key"]),
                {"project_key": str(row["project_key"]), "project": str(row["project"])},
            )
        selected_projects = sorted(catalog.values(), key=lambda item: item["project"].casefold())
        selected_keys = tuple(str(project["project_key"]) for project in selected_projects)

    project_order = {
        str(project["project_key"]): index for index, project in enumerate(selected_projects)
    }
    grouped: defaultdict[tuple[int | None, str, date], list[Any]] = defaultdict(list)
    for row in rows:
        grouped[(row["contributor_id"], row["contributor"] or "Unresolved", row["local_date"])].append(
            row
        )

    combined_intervals: list[dict[str, Any]] = []
    contributor_days: list[dict[str, Any]] = []
    for (contributor_id, contributor, local_date), interval_rows in grouped.items():
        events: defaultdict[datetime, dict[str, list[Any]]] = defaultdict(
            lambda: {"starts": [], "ends": []}
        )
        for row in interval_rows:
            if row["ended_at"] <= row["started_at"]:
                continue
            events[row["started_at"]]["starts"].append(row)
            events[row["ended_at"]]["ends"].append(row)
        active: dict[int, Any] = {}
        previous_at: datetime | None = None
        day_intervals: list[dict[str, Any]] = []
        for boundary in sorted(events):
            if previous_at is not None and boundary > previous_at and active:
                projects = {
                    str(row["project_key"]): str(row["project"]) for row in active.values()
                }
                project_items = [
                    {"project_key": key, "project": name}
                    for key, name in sorted(
                        projects.items(),
                        key=lambda item: (project_order.get(item[0], len(project_order)), item[1]),
                    )
                ]
                seconds = int((boundary - previous_at).total_seconds())
                value = {
                    "date": local_date.isoformat(),
                    "started_at": previous_at,
                    "ended_at": boundary,
                    "exact_seconds": seconds,
                    "contributor_id": contributor_id,
                    "contributor": contributor,
                    "projects": project_items,
                    "ambiguous": any(bool(row["ambiguous"]) for row in active.values()),
                    "source_interval_ids": sorted(active),
                }
                if (
                    day_intervals
                    and day_intervals[-1]["ended_at"] == value["started_at"]
                    and day_intervals[-1]["projects"] == value["projects"]
                    and day_intervals[-1]["ambiguous"] == value["ambiguous"]
                ):
                    day_intervals[-1]["ended_at"] = value["ended_at"]
                    day_intervals[-1]["exact_seconds"] += seconds
                    day_intervals[-1]["source_interval_ids"] = sorted(
                        set(day_intervals[-1]["source_interval_ids"])
                        | set(value["source_interval_ids"])
                    )
                else:
                    day_intervals.append(value)
            for row in events[boundary]["ends"]:
                active.pop(int(row["id"]), None)
            for row in events[boundary]["starts"]:
                active[int(row["id"])] = row
            previous_at = boundary

        raw_seconds = sum(int(row["exact_seconds"]) for row in interval_rows)
        exact_seconds = sum(int(item["exact_seconds"]) for item in day_intervals)
        contributor_days.append(
            {
                "date": local_date.isoformat(),
                "contributor_id": contributor_id,
                "contributor": contributor,
                "exact_seconds": exact_seconds,
                "raw_seconds": raw_seconds,
                "overlap_seconds": max(raw_seconds - exact_seconds, 0),
                "evidence_count": sum(int(row["evidence_count"]) for row in interval_rows),
            }
        )
        combined_intervals.extend(day_intervals)

    daily: dict[str, dict[str, Any]] = {}
    for item in contributor_days:
        day = daily.setdefault(
            item["date"],
            {
                "date": item["date"],
                "exact_seconds": 0,
                "raw_seconds": 0,
                "overlap_seconds": 0,
                "evidence_count": 0,
                "contributor_count": 0,
            },
        )
        day["exact_seconds"] += item["exact_seconds"]
        day["raw_seconds"] += item["raw_seconds"]
        day["overlap_seconds"] += item["overlap_seconds"]
        day["evidence_count"] += item["evidence_count"]
        day["contributor_count"] += 1

    contributor_totals: dict[tuple[int | None, str], dict[str, Any]] = {}
    for item in contributor_days:
        key = (item["contributor_id"], item["contributor"])
        total = contributor_totals.setdefault(
            key,
            {
                "contributor_id": item["contributor_id"],
                "contributor": item["contributor"],
                "exact_seconds": 0,
                "raw_seconds": 0,
                "overlap_seconds": 0,
                "active_days": 0,
            },
        )
        total["exact_seconds"] += item["exact_seconds"]
        total["raw_seconds"] += item["raw_seconds"]
        total["overlap_seconds"] += item["overlap_seconds"]
        total["active_days"] += 1

    exact_seconds = sum(int(item["exact_seconds"]) for item in contributor_days)
    raw_seconds = sum(int(item["raw_seconds"]) for item in contributor_days)
    calculation_key = stable_hash(
        "\0".join(
            (
                "combined-timesheet-v1",
                str(snapshot["id"]),
                str(snapshot["snapshot_key"]),
                str(snapshot["completed_at"]),
                financial_year,
                *sorted(selected_keys),
            )
        )
    )
    return {
        "calculation_key": calculation_key,
        "snapshot": snapshot,
        "financial_year": financial_year,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "projects": selected_projects,
        "project_keys": list(selected_keys),
        "exact_seconds": exact_seconds,
        "raw_seconds": raw_seconds,
        "overlap_seconds": max(raw_seconds - exact_seconds, 0),
        "multi_project_seconds": sum(
            int(item["exact_seconds"]) for item in combined_intervals if len(item["projects"]) > 1
        ),
        "active_days": len(daily),
        "interval_count": len(combined_intervals),
        "evidence_count": sum(int(item["evidence_count"]) for item in contributor_days),
        "days": sorted(daily.values(), key=lambda item: item["date"]),
        "contributor_days": sorted(
            contributor_days,
            key=lambda item: (item["date"], item["contributor"], item["contributor_id"] or -1),
        ),
        "contributors": sorted(
            contributor_totals.values(),
            key=lambda item: (item["contributor"], item["contributor_id"] or -1),
        ),
        "intervals": combined_intervals,
    }


def list_timesheet_rows(
    connection: Session,
    *,
    snapshot_id: int | None = None,
    filters: TimesheetFilters | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    filters = filters or TimesheetFilters()
    if snapshot_id is None:
        snapshot = latest_snapshot(connection)
        if snapshot is None:
            return []
        snapshot_id = int(snapshot["id"])
    clauses = ["interval.snapshot_id=?"]
    parameters: list[Any] = [snapshot_id]
    mapping = (
        ("interval.local_date>=?", filters.date_from),
        ("interval.local_date<=?", filters.date_to),
        ("contributor.display_name=?", filters.contributor),
        ("(project.project_key=? OR project.name=?)", filters.project),
        ("(activity.code=? OR activity.title=?)", filters.activity),
        ("COALESCE(activity.classification, 'unclassified')=?", filters.classification),
    )
    for clause, value in mapping:
        if value is None:
            continue
        clauses.append(clause)
        parameters.extend([value] * clause.count("?"))
    if filters.projects:
        projects = tuple(dict.fromkeys(filters.projects))
        placeholders = ", ".join("?" for _ in projects)
        clauses.append(
            f"(project.project_key IN ({placeholders}) OR project.name IN ({placeholders}))"
        )
        parameters.extend(projects)
        parameters.extend(projects)
    pagination = ""
    if limit is not None:
        pagination = "LIMIT ? OFFSET ?"
        parameters.extend([min(max(limit, 1), 2000), max(offset, 0)])
    return [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT interval.id, interval.local_date, interval.started_at, interval.ended_at,
                   interval.exact_seconds, interval.ambiguous, interval.ambiguity_reason,
                   interval.evidence_count,
                   contributor.display_name AS contributor,
                   project.project_key, project.name AS project,
                   activity.code AS activity, activity.title AS activity_title,
                   COALESCE(activity.classification, 'unclassified') AS classification
            FROM work_intervals interval
            LEFT JOIN contributors contributor ON contributor.id=interval.contributor_id
            LEFT JOIN projects project ON project.id=interval.project_id
            LEFT JOIN activities activity ON activity.id=interval.activity_id
            WHERE {" AND ".join(clauses)}
            ORDER BY interval.local_date, contributor.display_name NULLS LAST,
                     project.name NULLS LAST, activity.code NULLS LAST, interval.started_at
            {pagination}
            """,
            parameters,
        )
    ]


def export_timesheet(
    connection: Session,
    *,
    format: Literal["csv", "markdown", "json"] = "csv",
    snapshot_id: int | None = None,
    filters: TimesheetFilters | None = None,
) -> ExportResult:
    filters = filters or TimesheetFilters()
    snapshot = (
        dict(connection.execute("SELECT * FROM timesheet_snapshots WHERE id=?", (snapshot_id,)).fetchone())
        if snapshot_id is not None
        else latest_snapshot(connection)
    )
    if snapshot is None or snapshot["status"] != "complete":
        raise ValueError("no complete timesheet snapshot is available")
    rows = list_timesheet_rows(connection, snapshot_id=int(snapshot["id"]), filters=filters)
    if format == "csv":
        content = _csv(rows)
    elif format == "markdown":
        content = _markdown(connection, snapshot, rows)
    elif format == "json":
        content = b""  # the manifest below is the JSON export
    else:  # pragma: no cover - Literal and CLI validation guard this
        raise ValueError(f"unsupported export format: {format}")
    content_hash = hashlib.sha256(content).hexdigest() if format != "json" else None
    manifest = {
        "snapshot_key": snapshot["snapshot_key"],
        "corpus_fingerprint": snapshot["corpus_fingerprint"],
        "calculation_version": snapshot["algorithm_version"],
        "cutoff": snapshot["cutoff"].isoformat(),
        "generated_at": snapshot["generated_at"].isoformat(),
        "format": format,
        "filters": _filter_manifest(filters),
        "row_count": len(rows),
        "content_sha256": content_hash,
    }
    encoded_without_hash = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_sha256"] = hashlib.sha256(encoded_without_hash).hexdigest()
    if format == "json":
        content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        content_hash = hashlib.sha256(content).hexdigest()
    connection.execute(
        """
        INSERT INTO export_manifests(
            snapshot_id, format, filters_json, content_sha256, manifest_sha256
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            snapshot["id"],
            format,
            json.dumps(manifest["filters"], sort_keys=True),
            content_hash,
            manifest["manifest_sha256"],
        ),
    )
    connection.commit()
    return ExportResult(content=content, manifest=manifest)


def work_trail(
    connection: Session,
    *,
    project: str | None = None,
    activity: str | None = None,
    classification: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    clauses = ["true"]
    parameters: list[Any] = []
    if project:
        clauses.append("(project.project_key=? OR project.name=?)")
        parameters.extend([project, project])
    if activity:
        clauses.append("(activity.code=? OR activity.title=?)")
        parameters.extend([activity, activity])
    if classification:
        clauses.append("COALESCE(activity.classification, 'unclassified')=?")
        parameters.append(classification)
    parameters.append(min(max(limit, 1), 2000))
    return [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT episode.id AS episode_id, episode.episode_key, episode.started_at,
                   episode.ended_at, episode.evidence_state, episode.error_count,
                   session.session_key, session.provider,
                   contributor.display_name AS contributor,
                   project.project_key, project.name AS project,
                   activity.code AS activity, activity.title AS activity_title,
                   COALESCE(activity.classification, 'unclassified') AS classification,
                   left(goal.text, 240) AS goal, left(outcome.text, 240) AS outcome,
                   first_event.raw_record_id, raw.payload_hash AS provenance_hash
            FROM episodes episode
            JOIN sessions session ON session.id=episode.session_id
            JOIN events first_event ON first_event.id=episode.first_event_id
            JOIN raw_records raw ON raw.id=first_event.raw_record_id
            LEFT JOIN contributors contributor ON contributor.id=session.contributor_id
            LEFT JOIN contents goal ON goal.id=episode.goal_content_id
            LEFT JOIN contents outcome ON outcome.id=episode.outcome_content_id
            LEFT JOIN occurrence_activity_overrides override ON override.episode_key=episode.episode_key
            LEFT JOIN projects project ON project.id=COALESCE(override.project_id, session.project_id)
            LEFT JOIN LATERAL (
                SELECT a.id, a.code, a.title, a.classification
                FROM activities a
                WHERE a.id=COALESCE(
                    override.activity_id,
                    (
                        SELECT defaults.activity_id FROM project_default_activities defaults
                        WHERE defaults.project_id=session.project_id
                          AND COALESCE(episode.started_at, clock_timestamp()) >= defaults.effective_from
                          AND COALESCE(episode.started_at, clock_timestamp()) < defaults.effective_to
                        ORDER BY defaults.effective_from DESC LIMIT 1
                    )
                )
            ) activity ON true
            WHERE {" AND ".join(clauses)}
            ORDER BY episode.started_at DESC NULLS LAST, episode.id DESC LIMIT ?
            """,
            parameters,
        )
    ]


def _event_points(connection: Session, cutoff: datetime) -> list[EventPoint]:
    rows = connection.execute(
        """
        SELECT event.id AS event_id, event.session_id, event.timestamp,
               session.provider, session.external_id, session.parent_session_id,
               session.machine_id, session.contributor_id,
               COALESCE(occurrence.project_id, session.project_id) AS project_id,
               EXISTS (
                   SELECT 1 FROM text_units unit
                   WHERE unit.event_id=event.id AND unit.kind='user-message'
               ) AS direct_user
        FROM events event
        JOIN sessions session ON session.id=event.session_id
        LEFT JOIN LATERAL (
            SELECT override.project_id
            FROM episode_events link
            JOIN episodes episode ON episode.id=link.episode_id
            JOIN occurrence_activity_overrides override
              ON override.episode_key=episode.episode_key
            WHERE link.event_id=event.id AND override.project_id IS NOT NULL
            ORDER BY episode.id LIMIT 1
        ) occurrence ON true
        WHERE event.canonical_event_id IS NULL AND event.timestamp IS NOT NULL
          AND event.timestamp<=?
          AND event.event_type NOT IN ('compacted', 'parse-error')
        ORDER BY event.timestamp, event.id
        """,
        (cutoff,),
    ).fetchall()
    by_external = {(row["provider"], row["external_id"]): int(row["session_id"]) for row in rows}
    parent_by_session = {
        int(row["session_id"]): by_external.get((row["provider"], row["parent_session_id"]))
        for row in rows
        if row["parent_session_id"]
    }

    def root(session_id: int) -> int:
        seen: set[int] = set()
        current = session_id
        while current in parent_by_session and current not in seen:
            seen.add(current)
            current = int(parent_by_session[current])
        return current

    result = []
    for row in rows:
        session_id = int(row["session_id"])
        contributor_id = int(row["contributor_id"]) if row["contributor_id"] is not None else None
        contributor_key = (
            f"contributor:{contributor_id}"
            if contributor_id is not None
            else f"unresolved:{row['machine_id']}"
        )
        result.append(
            EventPoint(
                event_id=int(row["event_id"]),
                session_id=session_id,
                root_session_id=root(session_id),
                contributor_key=contributor_key,
                contributor_id=contributor_id,
                project_id=int(row["project_id"]) if row["project_id"] is not None else None,
                timestamp=_utc(row["timestamp"]),
                direct_user=bool(row["direct_user"]),
            )
        )
    return result


def _segments(points: list[EventPoint]) -> list[Segment]:
    grouped: defaultdict[tuple[str, int, int | None], list[EventPoint]] = defaultdict(list)
    for point in points:
        grouped[(point.contributor_key, point.root_session_id, point.project_id)].append(point)
    result: list[Segment] = []
    for events in grouped.values():
        events.sort(key=lambda item: (item.timestamp, item.event_id))
        activity_groups: list[list[EventPoint]] = []
        current: list[EventPoint] = []
        for event in events:
            if current and event.timestamp - current[-1].timestamp > INACTIVITY_GAP:
                activity_groups.append(current)
                current = []
            current.append(event)
        if current:
            activity_groups.append(current)
        for activity_group in activity_groups:
            result.append(
                Segment(
                    contributor_key=activity_group[0].contributor_key,
                    contributor_id=activity_group[0].contributor_id,
                    project_id=activity_group[0].project_id,
                    start=activity_group[0].timestamp,
                    end=activity_group[-1].timestamp,
                    event_ids={item.event_id for item in activity_group},
                    user_times=[item.timestamp for item in activity_group if item.direct_user],
                    event_times={item.event_id: item.timestamp for item in activity_group},
                )
            )
    return result


def _allocate_slices(segments: list[Segment], *, unallocated_id: int) -> list[Slice]:
    grouped: defaultdict[tuple[str, int | None], list[Segment]] = defaultdict(list)
    for segment in segments:
        grouped[(segment.contributor_key, segment.project_id)].append(segment)
    result: list[Slice] = []
    for (contributor_key, source_project_id), project_segments in grouped.items():
        contributor_id = project_segments[0].contributor_id
        project_id = source_project_id or unallocated_id
        ambiguous = source_project_id is None
        reason = "unresolved project" if ambiguous else None
        positive = [item for item in project_segments if item.end > item.start]
        boundaries = sorted({item.start for item in positive} | {item.end for item in positive})
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            active = [item for item in positive if item.start <= start and item.end >= end]
            if not active or end <= start:
                continue
            event_ids: set[int] = set()
            for segment in active:
                if not segment.event_times:
                    event_ids.update(segment.event_ids)
                    continue
                event_ids.update(
                    event_id
                    for event_id, timestamp in segment.event_times.items()
                    if start <= timestamp < end
                    or (timestamp == end and end == segment.end)
                )
            _append_or_merge(
                result,
                Slice(
                    contributor_key,
                    contributor_id,
                    project_id,
                    start,
                    end,
                    ambiguous,
                    reason,
                    event_ids,
                ),
            )
        # Preserve isolated evidence at zero duration without duplicating identical
        # repository clock points from parallel root chats.
        isolated: defaultdict[datetime, set[int]] = defaultdict(set)
        for segment in project_segments:
            if segment.start == segment.end:
                isolated[segment.start].update(segment.event_ids)
        for timestamp, event_ids in isolated.items():
            result.append(
                Slice(
                    contributor_key,
                    contributor_id,
                    project_id,
                    timestamp,
                    timestamp,
                    ambiguous,
                    reason,
                    event_ids,
                )
            )
    result.sort(key=lambda item: (item.contributor_key, item.start, item.end, item.project_id or -1))
    return result


def _append_or_merge(result: list[Slice], value: Slice) -> None:
    if result:
        previous = result[-1]
        if (
            previous.contributor_key == value.contributor_key
            and previous.end == value.start
            and previous.project_id == value.project_id
            and previous.ambiguous == value.ambiguous
            and previous.reason == value.reason
        ):
            previous.end = value.end
            previous.event_ids.update(value.event_ids)
            return
    result.append(value)


def _split_local_midnights(
    slices: list[Slice], *, zone: ZoneInfo | None = None
) -> list[Slice]:
    zone = zone or _local_zone()
    result: list[Slice] = []
    for item in slices:
        cursor = item.start
        while cursor < item.end:
            local = cursor.astimezone(zone)
            next_date = local.date() + timedelta(days=1)
            midnight = datetime.combine(next_date, time.min, tzinfo=zone).astimezone(UTC)
            end = min(item.end, midnight)
            result.append(
                Slice(
                    item.contributor_key,
                    item.contributor_id,
                    item.project_id,
                    cursor,
                    end,
                    item.ambiguous,
                    item.reason,
                    set(item.event_ids),
                )
            )
            cursor = end
        if item.start == item.end:
            result.append(item)
    return result


def _persist_intervals(
    connection: Session,
    snapshot_id: int,
    slices: list[Slice],
    *,
    zone: ZoneInfo | None = None,
) -> list[dict[str, Any]]:
    zone = zone or _local_zone()
    result: list[dict[str, Any]] = []
    last_end: dict[tuple[str, int], datetime] = {}
    assignment_slices = [
        part
        for item in slices
        for part in _split_default_activity_boundaries(connection, item)
    ]
    for item in assignment_slices:
        clock_key = (item.contributor_key, item.project_id or -1)
        if item.end > item.start and item.start < last_end.get(clock_key, item.start):
            raise RuntimeError(
                f"overlapping calculated intervals for {item.contributor_key} "
                f"and project {item.project_id}"
            )
        if item.end > item.start:
            last_end[clock_key] = max(last_end.get(clock_key, item.end), item.end)
        activity_id, activity_ambiguous = _activity_for_slice(connection, item)
        if activity_ambiguous:
            item.ambiguous = True
            conflict = "multiple occurrence activity overrides"
            item.reason = f"{item.reason}; {conflict}" if item.reason else conflict
        seconds = int((item.end - item.start).total_seconds())
        row = connection.execute(
            """
            INSERT INTO work_intervals(
                snapshot_id, contributor_id, project_id, activity_id, local_date,
                started_at, ended_at, exact_seconds, ambiguous, ambiguity_reason,
                evidence_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """,
            (
                snapshot_id,
                item.contributor_id,
                item.project_id,
                activity_id,
                item.start.astimezone(zone).date(),
                item.start,
                item.end,
                seconds,
                item.ambiguous,
                item.reason,
                len(item.event_ids),
            ),
        ).fetchone()
        assert row is not None
        interval_id = int(row["id"])
        evidence = connection.execute(
            """
            SELECT event.id AS event_id, episode.episode_key
            FROM events event
            LEFT JOIN episode_events link ON link.event_id=event.id
            LEFT JOIN episodes episode ON episode.id=link.episode_id
            WHERE event.id=ANY(?)
            """,
            (list(item.event_ids),),
        ).fetchall()
        connection.executemany(
            """
            INSERT INTO work_interval_evidence(interval_id, event_id, episode_key)
            VALUES (?, ?, ?) ON CONFLICT DO NOTHING
            """,
            [(interval_id, row["event_id"], row["episode_key"]) for row in evidence],
        )
        result.append({"id": interval_id, "seconds": seconds, "ambiguous": int(item.ambiguous)})
    connection.commit()
    return result


def _activity_for_slice(connection: Session, item: Slice) -> tuple[int | None, bool]:
    override = connection.execute(
        """
        SELECT DISTINCT override.activity_id
        FROM occurrence_activity_overrides override
        JOIN episode_events link ON link.episode_id=(
            SELECT id FROM episodes WHERE episode_key=override.episode_key
        )
        WHERE link.event_id=ANY(?)
        """,
        (list(item.event_ids),),
    ).fetchall()
    if len(override) == 1:
        return int(override[0]["activity_id"]), False
    if len(override) > 1:
        return None, True
    row = connection.execute(
        """
        SELECT activity_id FROM project_default_activities
        WHERE project_id=? AND ?>=effective_from AND ?<effective_to
        ORDER BY effective_from DESC LIMIT 1
        """,
        (item.project_id, item.start, item.start),
    ).fetchone()
    return (int(row["activity_id"]) if row is not None else None), False


def _split_default_activity_boundaries(connection: Session, item: Slice) -> list[Slice]:
    if item.end <= item.start:
        return [item]
    boundaries = [item.start]
    rows = connection.execute(
        """
        SELECT effective_from AS boundary FROM project_default_activities
        WHERE project_id=? AND effective_from>? AND effective_from<?
        UNION
        SELECT effective_to AS boundary FROM project_default_activities
        WHERE project_id=? AND effective_to>? AND effective_to<?
        """,
        (
            item.project_id,
            item.start,
            item.end,
            item.project_id,
            item.start,
            item.end,
        ),
    )
    for row in rows:
        boundaries.append(row["boundary"])
    boundaries.append(item.end)
    boundaries = sorted(set(boundaries))
    return [
        Slice(
            item.contributor_key,
            item.contributor_id,
            item.project_id,
            start,
            end,
            item.ambiguous,
            item.reason,
            set(item.event_ids),
        )
        for start, end in zip(boundaries, boundaries[1:], strict=False)
    ]


def _unallocated_project(connection: Session) -> int:
    key = stable_hash("project\0unallocated")
    row = connection.execute(
        """
        INSERT INTO projects(project_key, name, is_unresolved)
        VALUES (?, 'Unallocated', true)
        ON CONFLICT (project_key) DO UPDATE SET name=EXCLUDED.name
        RETURNING id
        """,
        (key,),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def _csv(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "date",
        "contributor",
        "project",
        "activity",
        "classification",
        "hours",
        "ambiguity",
        "evidence_count",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in _aggregate_export_rows(rows):
        writer.writerow(
            {
                "date": row["local_date"].isoformat(),
                "contributor": row["contributor"] or "Unresolved",
                "project": row["project"] or "Unallocated",
                "activity": row["activity"] or "Unclassified",
                "classification": row["classification"],
                "hours": f"{int(row['exact_seconds']) / 3600:.6f}",
                "ambiguity": "yes" if row["ambiguous"] else "no",
                "evidence_count": row["evidence_count"],
            }
        )
    return output.getvalue().encode()


def _aggregate_export_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["local_date"],
            row["contributor"],
            row["project"],
            row["activity"],
            row["classification"],
        )
        aggregate = grouped.setdefault(
            key,
            {
                "local_date": row["local_date"],
                "contributor": row["contributor"],
                "project": row["project"],
                "activity": row["activity"],
                "classification": row["classification"],
                "exact_seconds": 0,
                "ambiguous": False,
                "evidence_count": 0,
            },
        )
        aggregate["exact_seconds"] += int(row["exact_seconds"])
        aggregate["ambiguous"] = bool(aggregate["ambiguous"] or row["ambiguous"])
        aggregate["evidence_count"] += int(row["evidence_count"])
    return list(grouped.values())


def _markdown(
    connection: Session, snapshot: dict[str, Any], rows: list[dict[str, Any]]
) -> bytes:
    lines = [
        "# Chat-active work evidence",
        "",
        f"Snapshot: `{snapshot['snapshot_key']}`  ",
        f"Cutoff: `{snapshot['cutoff'].isoformat()}`  ",
        f"Corpus fingerprint: `{snapshot['corpus_fingerprint']}`",
        "",
        "| Date | Contributor | Project | Activity | Class | Hours | Ambiguous | Evidence |",
        "|---|---|---|---|---|---:|---|---:|",
    ]
    for row in rows:
        evidence = connection.execute(
            """
            SELECT DISTINCT evidence.episode_key, evidence.event_id,
                   episode.id AS episode_id
            FROM work_interval_evidence evidence
            LEFT JOIN episodes episode ON episode.episode_key=evidence.episode_key
            WHERE evidence.interval_id=?
            ORDER BY evidence.episode_key NULLS LAST, evidence.event_id LIMIT 100
            """,
            (row["id"],),
        ).fetchall()
        links = []
        for item in evidence:
            if item["episode_key"] and item["episode_id"]:
                links.append(
                    f"[occurrence {item['episode_key'][:12]}](/episodes/{item['episode_id']})"
                )
            else:
                links.append(f"[event {item['event_id']}](/api/events/{item['event_id']}/raw)")
        lines.append(
            "| "
            + " | ".join(
                (
                    row["local_date"].isoformat(),
                    str(row["contributor"] or "Unresolved"),
                    str(row["project"] or "Unallocated"),
                    str(row["activity"] or "Unclassified"),
                    str(row["classification"]),
                    f"{int(row['exact_seconds']) / 3600:.6f}",
                    "yes" if row["ambiguous"] else "no",
                    ", ".join(dict.fromkeys(links)) or "none",
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "This is an evidence-organizing aid. Chat-active time is not a payroll, "
            "billing, or attendance claim.",
            "",
        ]
    )
    return "\n".join(lines).encode()


def _filter_manifest(filters: TimesheetFilters) -> dict[str, Any]:
    return {
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "contributor": filters.contributor,
        "project": filters.project,
        "projects": list(filters.projects) or None,
        "activity": filters.activity,
        "classification": filters.classification,
    }


def _summary(row: dict[str, Any], *, reused: bool = False) -> TimesheetBuildSummary:
    return TimesheetBuildSummary(
        snapshot_id=int(row["id"]),
        snapshot_key=row["snapshot_key"],
        intervals=int(row["interval_count"]),
        total_seconds=int(row["total_seconds"]),
        ambiguity_count=int(row["ambiguity_count"]),
        corpus_fingerprint=row["corpus_fingerprint"],
        cutoff=_utc(row["cutoff"]),
        reused=reused,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _local_zone(value: str | None = None) -> ZoneInfo:
    name = (value or os.environ.get("CHATREVIEW_TIMEZONE") or os.environ.get("TZ") or "UTC").strip()
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise ValueError(f"unknown CHATREVIEW_TIMEZONE: {name}") from exc


def financial_year_dates(value: str) -> tuple[date, date]:
    match = value.strip().replace("FY", "").replace("fy", "")
    if "-" in match:
        start_text, end_text = match.split("-", 1)
        start_year = int(start_text)
        end_year = int(end_text) if len(end_text) == 4 else (start_year // 100) * 100 + int(end_text)
    else:
        end_year = int(match)
        start_year = end_year - 1
    if end_year != start_year + 1:
        raise ValueError("financial year must be like 2025-26 or 2026")
    return date(start_year, 7, 1), date(end_year, 6, 30)


def _financial_year_for_date(value: date) -> str:
    start_year = value.year if value.month >= 7 else value.year - 1
    return _financial_year_label(start_year)


def _financial_year_label(start_year: int) -> str:
    return f"{start_year}-{str(start_year + 1)[-2:]}"
