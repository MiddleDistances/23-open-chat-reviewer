from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.registry import save_activity, set_project_default_activity
from chatreview.timesheets import (
    EventPoint,
    Segment,
    TimesheetFilters,
    _allocate_slices,
    _segments,
    _split_local_midnights,
    build_timesheet,
    compute_combined_timesheet,
    export_timesheet,
    list_timesheet_rows,
    timesheet_calendar,
)


def _point(event_id: int, minute: int, root: int = 1, project: int = 1) -> EventPoint:
    return EventPoint(
        event_id=event_id,
        session_id=root,
        root_session_id=root,
        contributor_key="contributor:1",
        contributor_id=1,
        project_id=project,
        timestamp=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(minutes=minute),
        direct_user=event_id == 1,
    )


def test_one_hour_gap_is_inclusive_but_larger_gap_splits() -> None:
    segments = _segments([_point(1, 0), _point(2, 60), _point(3, 121)])
    assert [(item.start, item.end) for item in segments] == [
        (_point(1, 0).timestamp, _point(2, 60).timestamp),
        (_point(3, 121).timestamp, _point(3, 121).timestamp),
    ]


def test_cross_project_overlap_keeps_independent_repository_clocks() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    segments = [
        Segment(
            "contributor:1",
            1,
            10,
            start,
            start + timedelta(minutes=30),
            {1, 2},
            [start],
        ),
        Segment(
            "contributor:1",
            1,
            20,
            start + timedelta(minutes=5),
            start + timedelta(minutes=25),
            {3, 4},
            [start + timedelta(minutes=10)],
        ),
    ]
    slices = _allocate_slices(segments, unallocated_id=99)
    assert [(item.project_id, int((item.end - item.start).total_seconds())) for item in slices] == [
        (10, 1_800),
        (20, 1_200),
    ]
    assert sum((item.end - item.start).total_seconds() for item in slices) == 3_000
    assert not any(item.ambiguous for item in slices)


def test_cross_project_tie_counts_time_for_each_repository() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    segments = [
        Segment("contributor:1", 1, 10, start, start + timedelta(minutes=10), {1}, []),
        Segment("contributor:1", 1, 20, start, start + timedelta(minutes=10), {2}, []),
    ]
    slices = _allocate_slices(segments, unallocated_id=99)
    assert [(item.project_id, item.ambiguous) for item in slices] == [(10, False), (20, False)]
    assert sum((item.end - item.start).total_seconds() for item in slices) == 1_200


def test_parallel_chats_for_same_repository_are_counted_once() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    segments = [
        Segment("contributor:1", 1, 10, start, start + timedelta(minutes=30), {1, 2}, []),
        Segment(
            "contributor:1",
            1,
            10,
            start + timedelta(minutes=5),
            start + timedelta(minutes=25),
            {3, 4},
            [],
        ),
    ]
    slices = _allocate_slices(segments, unallocated_id=99)
    assert len(slices) == 1
    assert slices[0].project_id == 10
    assert (slices[0].end - slices[0].start).total_seconds() == 1_800
    assert slices[0].event_ids == {1, 2, 3, 4}


def test_other_repository_events_do_not_bridge_a_one_hour_gap() -> None:
    segments = _segments(
        [_point(1, 0, project=10), _point(2, 60, project=20), _point(3, 120, project=10)]
    )
    project_ten = [item for item in segments if item.project_id == 10]
    assert len(project_ten) == 2
    assert all(item.start == item.end for item in project_ten)


def test_intervals_split_at_australia_perth_midnight() -> None:
    item = Segment(
        "contributor:1",
        1,
        10,
        datetime(2026, 7, 1, 15, 55, tzinfo=UTC),
        datetime(2026, 7, 1, 16, 5, tzinfo=UTC),
        {1, 2},
        [],
    )
    allocated = _allocate_slices([item], unallocated_id=99)
    split = _split_local_midnights(allocated, zone=ZoneInfo("Australia/Perth"))
    assert [int((part.end - part.start).total_seconds()) for part in split] == [300, 300]
    assert all(part.start.tzinfo is not None for part in split)


def test_snapshot_reconciles_to_repository_scoped_raw_evidence(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        summary = build_timesheet(
            connection, cutoff=datetime(2026, 7, 19, tzinfo=UTC)
        )
        rows = list_timesheet_rows(connection)
        assert summary.intervals == len(rows)
        assert summary.total_seconds == sum(int(row["exact_seconds"]) for row in rows)
        assert all(row["started_at"] <= row["ended_at"] for row in rows)

        by_contributor_project: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            key = (str(row["contributor"]), str(row["project_key"]))
            by_contributor_project.setdefault(key, []).append(row)
        for intervals in by_contributor_project.values():
            positive = [row for row in intervals if row["ended_at"] > row["started_at"]]
            positive.sort(key=lambda row: row["started_at"])
            assert all(
                left["ended_at"] <= right["started_at"]
                for left, right in zip(positive, positive[1:], strict=False)
            )

        archived = connection.execute(
            """
            SELECT raw.payload_hash, payload.payload FROM work_interval_evidence evidence
            JOIN events event ON event.id=evidence.event_id
            JOIN raw_records raw ON raw.id=event.raw_record_id
            JOIN raw_payloads payload ON payload.payload_hash=raw.payload_hash
            """
        ).fetchall()
        assert archived
        assert all(
            hashlib.sha256(bytes(row["payload"])).hexdigest() == row["payload_hash"]
            for row in archived
        )

        exported = export_timesheet(connection, format="csv")
        records = list(csv.DictReader(io.StringIO(exported.content.decode())))
        assert records
        assert abs(
            sum(float(row["hours"]) for row in records) - summary.total_seconds / 3600
        ) < 0.000002 * len(records)
        assert exported.manifest["corpus_fingerprint"] == summary.corpus_fingerprint


def test_calendar_groups_snapshot_by_local_day_and_project(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        summary = build_timesheet(
            connection, cutoff=datetime(2026, 7, 19, tzinfo=UTC)
        )
        calendar = timesheet_calendar(connection, financial_year="2026-27")

    assert calendar["financial_year"] == "2026-27"
    assert calendar["available_financial_years"] == ["2026-27"]
    assert calendar["date_from"] == "2026-07-01"
    assert calendar["date_to"] == "2027-06-30"
    assert sum(day["exact_seconds"] for day in calendar["days"]) == summary.total_seconds
    assert sum(project["exact_seconds"] for project in calendar["projects"]) == summary.total_seconds
    assert all(project["active_days"] >= 1 for project in calendar["projects"])
    assert all(project["evidence_kinds"] == ["chat"] for project in calendar["projects"])
    assert all(day["evidence_kinds"] == ["chat"] for day in calendar["days"])
    assert all(
        project["evidence_kinds"] == ["chat"]
        for day in calendar["days"]
        for project in day["projects"]
    )
    assert {tuple(project["providers"]) for project in calendar["projects"]} == {
        ("claude",),
        ("codex",),
    }
    assert all(
        project["machines"]
        == [
            {
                "machine_id": str(settings.machine_id),
                "machine_name": settings.machine_name,
            }
        ]
        for project in calendar["projects"]
    )
    assert all(day["projects"] for day in calendar["days"])


def test_combined_timesheet_unions_cross_project_intervals_per_contributor(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        summary = build_timesheet(connection, cutoff=datetime(2026, 7, 19, tzinfo=UTC))
        projects = connection.execute(
            "SELECT id, project_key, name FROM projects ORDER BY id LIMIT 2"
        ).fetchall()
        contributor = connection.execute("SELECT id FROM contributors LIMIT 1").fetchone()
        assert len(projects) == 2
        assert contributor is not None
        connection.execute("DELETE FROM work_intervals WHERE snapshot_id=?", (summary.snapshot_id,))
        start = datetime(2026, 7, 18, 1, tzinfo=UTC)
        connection.executemany(
            """
            INSERT INTO work_intervals(
                snapshot_id, contributor_id, project_id, local_date, started_at, ended_at,
                exact_seconds, evidence_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    summary.snapshot_id,
                    contributor["id"],
                    projects[0]["id"],
                    start.astimezone(ZoneInfo("Australia/Perth")).date(),
                    start,
                    start + timedelta(hours=2),
                    7_200,
                    2,
                ),
                (
                    summary.snapshot_id,
                    contributor["id"],
                    projects[1]["id"],
                    start.astimezone(ZoneInfo("Australia/Perth")).date(),
                    start + timedelta(hours=1),
                    start + timedelta(hours=3),
                    7_200,
                    2,
                ),
            ],
        )
        connection.commit()

        result = compute_combined_timesheet(
            connection,
            financial_year="2026-27",
            project_keys=tuple(project["project_key"] for project in projects),
        )

    assert result["raw_seconds"] == 14_400
    assert result["exact_seconds"] == 10_800
    assert result["overlap_seconds"] == 3_600
    assert result["active_days"] == 1
    assert result["days"] == [
        {
            "date": "2026-07-18",
            "exact_seconds": 10_800,
            "raw_seconds": 14_400,
            "overlap_seconds": 3_600,
            "evidence_count": 4,
            "contributor_count": 1,
        }
    ]
    assert [interval["exact_seconds"] for interval in result["intervals"]] == [
        3_600,
        3_600,
        3_600,
    ]
    assert [len(interval["projects"]) for interval in result["intervals"]] == [1, 2, 1]
    assert all(
        contributor_day["exact_seconds"] <= 24 * 60 * 60
        for contributor_day in result["contributor_days"]
    )


def test_combined_timesheet_rejects_an_unknown_snapshot(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root)]).run()
    with database(settings.database_url) as connection:
        build_timesheet(connection, cutoff=datetime(2026, 7, 19, tzinfo=UTC))

        with pytest.raises(ValueError, match="timesheet snapshot 999999 is not available"):
            compute_combined_timesheet(
                connection,
                financial_year="2026-27",
                snapshot_id=999_999,
            )


def test_effective_activity_change_splits_a_work_interval(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        project = connection.execute(
            "SELECT id, project_key FROM projects WHERE name='codex-project'"
        ).fetchone()
        assert project is not None
        first = save_activity(
            connection,
            code="CORE-1",
            title="First activity",
            classification="core",
            reporting_period_start=datetime(2026, 7, 1).date(),
            reporting_period_end=datetime(2027, 6, 30).date(),
        )
        second = save_activity(
            connection,
            code="CORE-2",
            title="Second activity",
            classification="core",
            reporting_period_start=datetime(2026, 7, 1).date(),
            reporting_period_end=datetime(2027, 6, 30).date(),
        )
        boundary = "2026-07-18T02:00:02+00:00"
        set_project_default_activity(
            connection,
            project_id=project["id"],
            activity_id=first["id"],
            effective_from="2020-01-01T00:00:00+00:00",
            effective_to=boundary,
        )
        set_project_default_activity(
            connection,
            project_id=project["id"],
            activity_id=second["id"],
            effective_from=boundary,
        )
        build_timesheet(connection, cutoff=datetime(2026, 7, 19, tzinfo=UTC))
        rows = list_timesheet_rows(
            connection,
            filters=TimesheetFilters(project=project["project_key"]),
        )
    assert {row["activity"] for row in rows if row["exact_seconds"]} == {"CORE-1", "CORE-2"}
    assert sum(row["exact_seconds"] for row in rows) == 3
