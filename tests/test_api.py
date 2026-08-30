from __future__ import annotations

from fastapi.testclient import TestClient

from chatreview.api import ProjectAliasInput, create_app
from chatreview.episodes import EpisodeBuilder
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter


def test_project_alias_accepts_gemini_provider() -> None:
    payload = ProjectAliasInput(
        project_id=1,
        path_prefix="/work/gemini-project",
        provider="gemini",
    )
    assert payload.provider == "gemini"


def test_api_search_transcript_and_annotations(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    client = TestClient(create_app(settings))
    stats = client.get("/api/stats")
    assert stats.status_code == 200
    assert stats.json()["events"] == 10

    response = client.get("/api/search", params={"q": "frobnicator", "mode": "lexical"})
    assert response.status_code == 200
    assert response.json()["lexical"]
    assert "text" not in response.json()["lexical"][0]
    assert response.json()["lexical"][0]["snippet"]
    event_id = response.json()["lexical"][0]["event_id"]
    event = client.get(f"/api/events/{event_id}")
    assert event.status_code == 200
    event_key = event.json()["event_key"]

    annotation = client.post(
        "/api/annotations",
        json={
            "target_type": "event",
            "target_key": event_key,
            "label": "failure",
            "note": "Repeated failure evidence",
            "review_state": "reviewed",
        },
    )
    assert annotation.status_code == 201
    listed = client.get("/api/annotations", params={"target_key": event_key})
    assert listed.json()[0]["label"] == "failure"
    assert listed.json()[0]["note"] == "Repeated failure evidence"

    raw = client.get(f"/api/events/{event_id}/raw")
    assert raw.status_code == 200
    assert raw.json()["valid"] is True


def test_setup_preview_and_map_date_validation(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    client = TestClient(create_app(settings))

    status = client.get("/api/setup/status")
    assert status.status_code == 200
    assert status.json()["machine"]["id"] == str(settings.machine_id)
    assert "postgresql" not in repr(status.json()).lower()

    preview = client.post(
        "/api/setup/preview",
        json={
            "history_start": "2026-07-18",
            "history_end": "2026-07-18",
            "providers": ["codex"],
            "include_git_metadata": False,
            "preserve_encrypted_reasoning": False,
            "include_readable_reasoning_in_search": True,
            "include_reasoning_in_projection": False,
        },
    )
    assert preview.status_code == 200
    assert preview.json()["scope_estimate"]["events"] > 0
    assert preview.json()["retention"] == {
        "preserve_encrypted_reasoning": False,
        "include_readable_reasoning_in_search": True,
        "include_reasoning_in_projection": False,
    }
    assert settings.database_url not in repr(preview.json())

    inverted = client.get(
        "/api/map",
        params={"date_from": "2026-08-30", "date_to": "2026-08-01"},
    )
    assert inverted.status_code == 422

    build = client.get("/api/setup/build")
    assert build.status_code == 200
    assert build.json()["status"] == "idle"
    assert "startedAt" in build.json()

    hidden_reasoning = client.get(
        "/api/search", params={"q": "assumption", "mode": "lexical"}
    )
    included_reasoning = client.get(
        "/api/search",
        params={"q": "assumption", "mode": "lexical", "include_reasoning": True},
    )
    assert hidden_reasoning.status_code == 200
    assert hidden_reasoning.json()["lexical"] == []
    assert included_reasoning.json()["lexical"]


def test_work_archive_registry_trail_timesheets_and_status(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    EpisodeBuilder(settings).run(force=True)
    client = TestClient(create_app(settings))

    projects = client.get("/api/projects")
    assert projects.status_code == 200
    project = next(item for item in projects.json() if item["name"] == "codex-project")
    alias = client.post(
        "/api/project-aliases",
        json={
            "project_id": project["id"],
            "machine_id": str(settings.machine_id),
            "provider": "claude",
            "path_prefix": "/work/claude-project",
            "alias": "renamed checkout",
        },
    )
    assert alias.status_code == 201
    listed_aliases = client.get("/api/project-aliases")
    assert listed_aliases.status_code == 200
    assert any(item["alias"] == "renamed checkout" for item in listed_aliases.json())
    rebuilt = client.post("/api/projects/rebuild")
    assert rebuilt.status_code == 202
    remapped_project = next(
        item for item in client.get("/api/projects").json() if item["id"] == project["id"]
    )
    assert remapped_project["session_count"] == 2

    activity = client.put(
        "/api/activities/EXP-2026-01",
        json={
            "code": "EXP-2026-01",
            "title": "Resolve deterministic parser uncertainty",
            "classification": "core",
            "reporting_period_start": "2026-07-01",
            "reporting_period_end": "2027-06-30",
            "description": "Controlled software experiment evidence.",
            "uncertainty_or_hypothesis": "Whether the parser can preserve exact evidence.",
        },
    )
    assert activity.status_code == 200
    default = client.put(
        f"/api/projects/{project['id']}/default-activity",
        json={
            "activity_id": activity.json()["id"],
            "effective_from": "2026-01-01T00:00:00Z",
        },
    )
    assert default.status_code == 200

    contributors = client.get("/api/contributors")
    assert contributors.status_code == 200
    assert contributors.json()[0]["display_name"] == "Test Contributor"
    rule = client.post(
        "/api/contributor-rules",
        json={
            "machine_id": str(settings.machine_id),
            "contributor_id": contributors.json()[0]["id"],
            "path_prefix": "/work",
        },
    )
    assert rule.status_code == 201

    trail = client.get("/api/work-trail")
    assert trail.status_code == 200
    assert trail.json()
    assert all(item["provenance_hash"] for item in trail.json())
    override_activity = client.put(
        "/api/activities/EXP-2026-02",
        json={
            "code": "EXP-2026-02",
            "title": "Occurrence-specific experiment",
            "classification": "supporting",
            "reporting_period_start": "2026-07-01",
            "reporting_period_end": "2027-06-30",
        },
    )
    target = next(item for item in trail.json() if "frobnicator" in (item["goal"] or ""))
    override = client.put(
        f"/api/occurrences/{target['episode_key']}/activity",
        json={
            "activity_id": override_activity.json()["id"],
            "project_id": project["id"],
            "note": "Specific supporting occurrence",
        },
    )
    assert override.status_code == 200
    assigned_search = client.get(
        "/api/search",
        params={"q": "frobnicator", "mode": "lexical", "activity": "EXP-2026-02"},
    )
    assert assigned_search.status_code == 200
    assert assigned_search.json()["hits"]
    assert all(item["activity"] == "EXP-2026-02" for item in assigned_search.json()["hits"])

    built = client.post(
        "/api/timesheets/build",
        params={"cutoff": "2026-07-19T00:00:00Z"},
    )
    assert built.status_code == 202
    timesheet = client.get("/api/timesheets")
    assert timesheet.status_code == 200
    assert timesheet.json()["snapshot"]["status"] == "complete"
    assert sum(row["exact_seconds"] for row in timesheet.json()["rows"]) == built.json()[
        "total_seconds"
    ]
    calendar = client.get(
        "/api/timesheets/calendar",
        params={"financial_year": "2026-27"},
    )
    assert calendar.status_code == 200
    assert calendar.json()["financial_year"] == "2026-27"
    assert calendar.json()["date_from"] == "2026-07-01"
    assert calendar.json()["date_to"] == "2027-06-30"
    assert sum(day["exact_seconds"] for day in calendar.json()["days"]) == built.json()[
        "total_seconds"
    ]
    assert calendar.json()["projects"]
    project_keys = [calendar.json()["projects"][0]["project_key"], "missing-project"]
    combined = client.post(
        "/api/timesheets/compute",
        json={
            "financial_year": "2026-27",
            "project_keys": [project_keys[0]],
        },
    )
    assert combined.status_code == 200
    assert combined.json()["project_keys"] == [project_keys[0]]
    assert combined.json()["exact_seconds"] <= combined.json()["raw_seconds"]
    assert all(
        item["exact_seconds"] <= 24 * 60 * 60
        for item in combined.json()["contributor_days"]
    )
    unknown_combined_project = client.post(
        "/api/timesheets/compute",
        json={"financial_year": "2026-27", "project_keys": ["missing-project"]},
    )
    assert unknown_combined_project.status_code == 422
    multi_project_timesheet = client.get(
        "/api/timesheets",
        params=[("projects", project_key) for project_key in project_keys],
    )
    assert multi_project_timesheet.status_code == 200
    assert {
        row["project_key"] for row in multi_project_timesheet.json()["rows"]
    } == {project_keys[0]}
    calendar_year = client.get("/api/timesheets/calendar", params={"year": 2026})
    assert calendar_year.status_code == 200
    assert calendar_year.json()["year"] == 2026
    assert calendar_year.json()["date_from"] == "2026-01-01"
    assert calendar_year.json()["date_to"] == "2026-12-31"
    invalid_calendar = client.get(
        "/api/timesheets/calendar",
        params={"financial_year": "2026-28"},
    )
    assert invalid_calendar.status_code == 422
    exported = client.get("/api/timesheets/export", params={"format": "json"})
    assert exported.status_code == 200
    assert exported.headers["x-chatreview-manifest-sha256"]

    archive = client.get("/api/archive-status")
    assert archive.status_code == 200
    assert archive.json()["raw_records"] == 10
    assert archive.json()["length_mismatches"] == 0
    assert "self-hosted PostgreSQL archive" in archive.json()["privacy"]
