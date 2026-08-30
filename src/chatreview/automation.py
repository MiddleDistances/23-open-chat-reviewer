"""Read-only health and refresh planning for unattended ChatReviewer jobs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from chatreview.db import Session
from chatreview.episodes import episode_stats
from chatreview.search import corpus_stats
from chatreview.semantic import corpus_revision
from chatreview.timesheets import ALGORITHM_VERSION as TIMESHEET_ALGORITHM_VERSION
from chatreview.timesheets import latest_snapshot

SEMANTIC_PROFILES = ("conversation", "episodes")


def _jsonable(value: Any) -> Any:
    """Convert PostgreSQL values into values suitable for a status report."""

    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        import json

        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _schema_value(connection: Session, key: str) -> str | None:
    row = connection.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row and row["value"] is not None else None


def _semantic_status(
    connection: Session,
    *,
    fingerprint: str,
    episode_generation: str | None,
) -> dict[str, dict[str, Any]]:
    """Summarise the latest complete and latest attempted semantic run per profile."""

    rows = connection.execute(
        """
        SELECT id, run_key, profile, model_name, model_revision, dimensions,
               chunk_count, status, is_active, started_at, completed_at, error, config_json
        FROM semantic_runs
        ORDER BY started_at DESC, id DESC
        """
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for profile in SEMANTIC_PROFILES:
        profile_rows = [row for row in rows if row["profile"] == profile]
        latest = profile_rows[0] if profile_rows else None
        complete = next((row for row in profile_rows if row["status"] == "complete"), None)
        item: dict[str, Any] = {
            "profile": profile,
            "latest_attempt": dict(latest) if latest is not None else None,
            "latest_complete": dict(complete) if complete is not None else None,
            "freshness": "missing",
        }
        if complete is not None:
            config = _decode_json(complete["config_json"])
            fresh = config.get("corpus_revision") == fingerprint
            if profile == "episodes" and config.get("episode_generation"):
                fresh = fresh and config["episode_generation"] == episode_generation
            item["freshness"] = "current" if fresh else "stale"
            item["recorded_corpus_fingerprint"] = config.get("corpus_revision")
            item["recorded_episode_generation"] = config.get("episode_generation")
        if latest is not None:
            latest_config = _decode_json(latest["config_json"])
            item["latest_attempt_profile"] = latest_config.get("profile", profile)
            item["latest_attempt_status"] = latest["status"]
            item["latest_attempt_error"] = latest["error"]
        result[profile] = _jsonable(item)
    return result


def automation_status(connection: Session) -> dict[str, Any]:
    """Return a deterministic, read-only status report for scheduled jobs.

    Work-activity classification is optional and never blocks archive freshness.
    """

    stats = corpus_stats(connection)
    fingerprint = corpus_revision(connection)
    episodes = episode_stats(connection)
    snapshot = latest_snapshot(connection)
    episode_revision = _schema_value(connection, "episode_corpus_revision")
    episode_generation = _schema_value(connection, "episode_generation")
    source_status_rows = connection.execute(
        """
        SELECT revision.status, COUNT(*) AS sources,
               COALESCE(SUM(revision.pending_length), 0) AS pending_bytes,
               COALESCE(SUM(revision.error_count), 0) AS parse_errors
        FROM sources source
        JOIN source_revisions revision ON revision.id=source.active_revision_id
        GROUP BY revision.status ORDER BY revision.status
        """
    ).fetchall()
    source_status = [dict(row) for row in source_status_rows]
    source_counts = {str(row["status"]): int(row["sources"]) for row in source_status_rows}
    pending_bytes = sum(int(row["pending_bytes"] or 0) for row in source_status_rows)
    parse_errors = sum(int(row["parse_errors"] or 0) for row in source_status_rows)

    event_range = dict(
        connection.execute(
            "SELECT MIN(timestamp) AS first_event, MAX(timestamp) AS last_event FROM events"
        ).fetchone()
    )
    latest_source = dict(
        connection.execute(
            """
            SELECT MAX(revision.updated_at) AS latest_revision_update,
                   MAX(revision.completed_at) AS latest_complete_revision,
                   MAX(revision.ingested_offset) AS largest_ingested_offset
            FROM sources source
            JOIN source_revisions revision ON revision.id=source.active_revision_id
            """
        ).fetchone()
    )
    activity_counts = {
        str(row["classification"]): int(row["activities"])
        for row in connection.execute(
            """
            SELECT classification, COUNT(*) AS activities
            FROM activities GROUP BY classification ORDER BY classification
            """
        ).fetchall()
    }
    activity_total = sum(activity_counts.values())
    defaults = int(connection.execute("SELECT COUNT(*) FROM project_default_activities").fetchone()[0])
    overrides = int(
        connection.execute("SELECT COUNT(*) FROM occurrence_activity_overrides").fetchone()[0]
    )

    unclassified_intervals = 0
    unclassified_seconds = 0
    if snapshot is not None:
        row = connection.execute(
            """
            SELECT COUNT(*) AS intervals,
                   COALESCE(SUM(exact_seconds), 0) AS exact_seconds
            FROM work_intervals
            WHERE snapshot_id=? AND activity_id IS NULL
            """,
            (snapshot["id"],),
        ).fetchone()
        unclassified_intervals = int(row["intervals"] or 0)
        unclassified_seconds = int(row["exact_seconds"] or 0)

    episodes_fresh = not stats["events"] or (
        episode_revision == fingerprint and int(episodes["episodes"] or 0) > 0
    )
    timesheet_fresh = bool(
        snapshot
        and snapshot["corpus_fingerprint"] == fingerprint
        and int(snapshot["algorithm_version"]) == TIMESHEET_ALGORITHM_VERSION
    )
    needs_episodes = bool(stats["events"] and not episodes_fresh)
    needs_timesheet = not timesheet_fresh
    semantic = _semantic_status(
        connection,
        fingerprint=fingerprint,
        episode_generation=episode_generation,
    )

    warnings: list[str] = []
    blocking_reasons: list[str] = []
    actions: list[str] = []
    if any(source_counts.get(status, 0) for status in ("partial", "ingesting", "pending")):
        warnings.append("active source revisions are incomplete or still ingesting")
        actions.append("allow the next sync cycle to ingest newly completed source lines")
    if source_counts.get("failed", 0):
        message = "one or more active source revisions failed"
        warnings.append(message)
        blocking_reasons.append(message)
        actions.append("inspect the sync log and repair or quarantine the failed source revision")
    if needs_episodes:
        warnings.append("derived episodes are stale relative to the active source catalog")
        actions.append("run the derived episode refresh")
    if snapshot is None:
        warnings.append("no complete timesheet snapshot exists")
        actions.append("run the timesheet refresh")
    elif needs_timesheet:
        warnings.append("latest timesheet snapshot is stale relative to the active source catalog")
        actions.append("run the timesheet refresh")
    for profile, item in semantic.items():
        if item.get("latest_attempt_status") == "failed":
            warnings.append(f"latest semantic {profile} attempt failed")
            actions.append(f"inspect the semantic {profile} job error before retrying")
        # Semantic search is an optional extra. A missing index is surfaced in
        # status but does not make the core archive unhealthy.
        if item["freshness"] == "stale":
            warnings.append(f"semantic {profile} index is {item['freshness']}")
            actions.append(f"run the guarded semantic {profile} refresh")

    if blocking_reasons:
        status = "blocked"
    elif warnings:
        status = "needs-attention"
    else:
        status = "healthy"

    return _jsonable(
        {
            "status": status,
            "generated_at": datetime.now().astimezone(),
            "corpus_fingerprint": fingerprint,
            "corpus": stats,
            "event_range": event_range,
            "latest_source": latest_source,
            "source_status": source_status,
            "source_counts": source_counts,
            "pending_bytes": pending_bytes,
            "parse_errors": parse_errors,
            "episodes": {
                **episodes,
                "corpus_revision": episode_revision,
                "generation": episode_generation,
                "fresh": episodes_fresh,
            },
            "timesheet": {
                "latest_snapshot": snapshot,
                "fresh": timesheet_fresh,
                "unclassified_intervals": unclassified_intervals,
                "unclassified_seconds": unclassified_seconds,
            },
            "activities": {
                "total": activity_total,
                "by_classification": activity_counts,
                "project_defaults": defaults,
                "occurrence_overrides": overrides,
            },
            "semantic": semantic,
            "refresh": {
                "safe": not blocking_reasons,
                "needs_episodes": needs_episodes,
                "needs_timesheet": needs_timesheet,
            },
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "recommended_actions": list(dict.fromkeys(actions)),
        }
    )
