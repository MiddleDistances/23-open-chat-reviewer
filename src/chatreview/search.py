from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from chatreview.db import Row, Session
from chatreview.providers.base import stable_hash

TOKEN_PATTERN = re.compile(r"[\w@./:-]+", re.UNICODE)


@dataclass(slots=True)
class SearchFilters:
    provider: str | None = None
    project: str | None = None
    contributor: str | None = None
    activity: str | None = None
    activity_classification: str | None = None
    role: str | None = None
    kind: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    errors_only: bool = False


def lexical_search(
    connection: Session,
    query: str,
    *,
    filters: SearchFilters | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Search every normalized text unit with PostgreSQL's `simple` dictionary."""

    filters = filters or SearchFilters()
    fts_query = build_fts_query(query)
    if not fts_query:
        return []
    clauses = [
        "e.canonical_event_id IS NULL",
        "c.search_vector @@ plainto_tsquery('simple', ?)",
    ]
    filter_parameters: list[Any] = []
    _append_filters(clauses, filter_parameters, filters)
    parameters = [
        fts_query,  # headline
        fts_query,  # rank
        fts_query,  # WHERE
        *filter_parameters,
        min(max(limit, 1), 500),
        max(offset, 0),
    ]
    rows = connection.execute(
        f"""
        SELECT
            'event' AS target_type,
            e.event_key AS target_key,
            e.id AS event_id,
            e.event_key,
            e.timestamp,
            e.event_type,
            e.subtype,
            e.role,
            e.line_no,
            e.byte_offset,
            e.byte_length,
            t.unit_key,
            t.kind,
            t.label,
            t.is_error,
            c.id AS content_id,
            c.text,
            ts_headline(
                'simple', c.text, plainto_tsquery('simple', ?),
                'StartSel=<mark>, StopSel=</mark>, MaxFragments=3, MaxWords=48, MinWords=12'
            ) AS snippet,
            ts_rank_cd(c.search_vector, plainto_tsquery('simple', ?))::double precision
                AS lexical_score,
            NULL::double precision AS semantic_score,
            s.id AS session_id,
            s.session_key,
            s.external_id AS session_external_id,
            s.provider,
            COALESCE(project.name, s.project) AS project,
            project.project_key,
            contributor.display_name AS contributor,
            activity.code AS activity,
            activity.title AS activity_title,
            activity.classification AS activity_classification,
            source.path AS source_path,
            rr.id AS raw_record_id,
            rr.payload_hash AS provenance_hash
        FROM contents c
        JOIN text_units t ON t.content_id=c.id
        JOIN events e ON e.id=t.event_id
        LEFT JOIN sessions s ON s.id=e.session_id
        JOIN sources source ON source.id=e.source_id
        JOIN raw_records rr ON rr.id=e.raw_record_id
        LEFT JOIN LATERAL (
            SELECT override.activity_id, override.project_id
            FROM episode_events link
            JOIN episodes episode ON episode.id=link.episode_id
            JOIN occurrence_activity_overrides override
              ON override.episode_key=episode.episode_key
            WHERE link.event_id=e.id
            ORDER BY episode.id LIMIT 1
        ) occurrence ON true
        LEFT JOIN projects project
          ON project.id=COALESCE(occurrence.project_id, s.project_id)
        LEFT JOIN contributors contributor ON contributor.id=s.contributor_id
        LEFT JOIN LATERAL (
            SELECT a.code, a.title, a.classification
            FROM activities a
            WHERE a.id=COALESCE(
                occurrence.activity_id,
                (
                    SELECT defaults.activity_id
                    FROM project_default_activities defaults
                    WHERE defaults.project_id=COALESCE(occurrence.project_id, s.project_id)
                      AND COALESCE(e.timestamp, clock_timestamp()) >= defaults.effective_from
                      AND COALESCE(e.timestamp, clock_timestamp()) < defaults.effective_to
                    ORDER BY defaults.effective_from DESC LIMIT 1
                )
            )
        ) activity ON true
        WHERE {" AND ".join(clauses)}
        ORDER BY lexical_score DESC, e.timestamp DESC NULLS LAST, e.id DESC
        LIMIT ? OFFSET ?
        """,
        parameters,
    ).fetchall()
    return [_row_dict(row) for row in rows]


def build_fts_query(query: str) -> str:
    """Bound untrusted lexical input before passing it to `plainto_tsquery`."""

    return " ".join(TOKEN_PATTERN.findall(query.strip())[:64])


def reciprocal_rank_fusion(
    lexical: list[dict[str, Any]],
    semantic: list[dict[str, Any]],
    *,
    limit: int,
    k: int = 60,
) -> list[dict[str, Any]]:
    """Combine equal-weight top candidate lists using Reciprocal Rank Fusion."""

    combined: dict[tuple[str, str], dict[str, Any]] = {}
    scores: defaultdict[tuple[str, str], float] = defaultdict(float)
    for candidates in (lexical[:100], semantic[:100]):
        for rank, item in enumerate(candidates, start=1):
            key = (str(item["target_type"]), str(item["target_key"]))
            scores[key] += 1.0 / (k + rank)
            current = combined.get(key)
            if current is None:
                combined[key] = dict(item)
            else:
                if item.get("lexical_score") is not None:
                    current["lexical_score"] = item["lexical_score"]
                if item.get("semantic_score") is not None:
                    current["semantic_score"] = item["semantic_score"]
    result = []
    for key, item in combined.items():
        item["rrf_score"] = scores[key]
        result.append(item)
    return sorted(
        result,
        key=lambda item: (-float(item["rrf_score"]), item["target_type"], item["target_key"]),
    )[: min(max(limit, 1), 500)]


def list_sessions(
    connection: Session,
    *,
    provider: str | None = None,
    project: str | None = None,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = ["true"]
    parameters: list[Any] = []
    if provider:
        clauses.append("s.provider=?")
        parameters.append(provider)
    if project:
        clauses.append("(project.project_key=? OR project.name=? OR s.project=?)")
        parameters.extend([project, project, project])
    if query:
        clauses.append(
            "(s.external_id ILIKE ? OR s.project ILIKE ? OR s.cwd ILIKE ? OR s.title ILIKE ?)"
        )
        pattern = f"%{query}%"
        parameters.extend([pattern] * 4)
    parameters.extend([min(max(limit, 1), 500), max(offset, 0)])
    rows = connection.execute(
        f"""
        SELECT s.id, s.session_key, s.provider, s.external_id,
               COALESCE(project.name, s.project) AS project, project.project_key,
               contributor.display_name AS contributor, s.cwd, s.started_at, s.ended_at,
               s.title, s.event_count, s.text_unit_count
        FROM sessions s
        LEFT JOIN projects project ON project.id=s.project_id
        LEFT JOIN contributors contributor ON contributor.id=s.contributor_id
        WHERE {" AND ".join(clauses)}
        ORDER BY COALESCE(s.ended_at, s.started_at) DESC NULLS LAST
        LIMIT ? OFFSET ?
        """,
        parameters,
    ).fetchall()
    return [_row_dict(row) for row in rows]


def session_events(
    connection: Session,
    session_id: int,
    *,
    limit: int = 500,
    offset: int = 0,
    include_empty: bool = False,
) -> list[dict[str, Any]]:
    empty_clause = "" if include_empty else "HAVING COUNT(t.id) > 0 OR e.parse_error IS NOT NULL"
    rows = connection.execute(
        f"""
        SELECT e.id, e.event_key, e.timestamp, e.event_type, e.subtype, e.role,
               e.provider_event_id, e.parent_event_id, e.turn_id, e.line_no,
               e.byte_offset, e.byte_length, e.parse_error, e.metadata_json,
               source.path AS source_path, revision.provenance_json AS source_provenance_json,
               e.raw_record_id,
               COUNT(t.id) AS text_unit_count
        FROM events e
        JOIN sources source ON source.id=e.source_id
        JOIN source_revisions revision ON revision.id=e.source_revision_id
        LEFT JOIN text_units t ON t.event_id=e.id
        WHERE e.session_id=?
        GROUP BY e.id, source.path, revision.provenance_json
        {empty_clause}
        ORDER BY e.timestamp NULLS FIRST, e.ordinal, e.id
        LIMIT ? OFFSET ?
        """,
        (session_id, min(max(limit, 1), 5000), max(offset, 0)),
    ).fetchall()
    result = []
    for row in rows:
        item = _row_dict(row)
        item["metadata"] = _parse_json(item.pop("metadata_json", {}))
        item["source_provenance"] = _parse_json(item.pop("source_provenance_json", {}))
        if item["text_unit_count"]:
            units = connection.execute(
                """
                SELECT t.unit_key, t.kind, t.label, t.is_error, c.text, c.char_count
                FROM text_units t JOIN contents c ON c.id=t.content_id
                WHERE t.event_id=? ORDER BY t.unit_index
                """,
                (row["id"],),
            ).fetchall()
            item["units"] = [_row_dict(unit) for unit in units]
        else:
            item["units"] = []
        result.append(item)
    return result


def get_event(connection: Session, event_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT e.*, source.path AS source_path, source.provider,
               revision.provenance_json AS source_provenance_json,
               s.session_key, s.external_id
        FROM events e
        JOIN sources source ON source.id=e.source_id
        JOIN source_revisions revision ON revision.id=e.source_revision_id
        LEFT JOIN sessions s ON s.id=e.session_id
        WHERE e.id=?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    item = _row_dict(row)
    item["metadata"] = _parse_json(item.pop("metadata_json", {}))
    item["source_provenance"] = _parse_json(item.pop("source_provenance_json", {}))
    item["units"] = [
        _row_dict(unit)
        for unit in connection.execute(
            """
            SELECT t.unit_key, t.kind, t.label, t.is_error, c.text, c.char_count
            FROM text_units t JOIN contents c ON c.id=t.content_id
            WHERE t.event_id=? ORDER BY t.unit_index
            """,
            (event_id,),
        ).fetchall()
    ]
    item["artifacts"] = [
        _row_dict(artifact)
        for artifact in connection.execute(
            "SELECT kind, label, value, value_hash FROM artifacts WHERE event_id=? ORDER BY id",
            (event_id,),
        ).fetchall()
    ]
    return item


def read_raw_event(
    connection: Session, event_id: int, *, max_bytes: int | None = 2_000_000
) -> dict[str, Any] | None:
    """Read exact archived bytes and verify SHA-256 before returning them."""

    row = connection.execute(
        """
        SELECT rr.id AS raw_record_id, rr.payload_hash, rr.byte_offset,
               rr.byte_length, rr.line_no, payload.payload, source.path,
               source.provider, source.source_kind, revision.provenance_json
        FROM events e
        JOIN raw_records rr ON rr.id=e.raw_record_id
        JOIN raw_payloads payload ON payload.payload_hash=rr.payload_hash
        JOIN sources source ON source.id=e.source_id
        JOIN source_revisions revision ON revision.id=e.source_revision_id
        WHERE e.id=?
        """,
        (event_id,),
    ).fetchone()
    if row is None:
        return None
    byte_length = int(row["byte_length"])
    if max_bytes is not None and byte_length > max_bytes:
        return {
            "available": True,
            "truncated": True,
            "path": row["path"],
            "provider": row["provider"],
            "source_kind": row["source_kind"],
            "source_provenance": _parse_json(row["provenance_json"]),
            "line_no": row["line_no"],
            "byte_length": byte_length,
            "reason": f"raw record exceeds the {max_bytes}-byte response limit",
        }
    raw = bytes(row["payload"])
    actual_hash = stable_hash(raw)
    valid = actual_hash == row["payload_hash"] and len(raw) == byte_length
    return {
        "available": True,
        "valid": valid,
        "path": row["path"],
        "provider": row["provider"],
        "source_kind": row["source_kind"],
        "source_provenance": _parse_json(row["provenance_json"]),
        "raw_record_id": row["raw_record_id"],
        "line_no": row["line_no"],
        "byte_offset": row["byte_offset"],
        "byte_length": byte_length,
        "expected_hash": row["payload_hash"],
        "actual_hash": actual_hash,
        "raw": raw.decode("utf-8", errors="replace") if valid else None,
        "reason": None if valid else "archived bytes do not match their SHA-256 identity",
    }


def corpus_stats(connection: Session) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for table in (
        "sources",
        "source_revisions",
        "raw_records",
        "raw_payloads",
        "sessions",
        "events",
        "contents",
        "text_units",
        "artifacts",
        "episodes",
        "annotations",
    ):
        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    counts["parse_errors"] = int(
        connection.execute("SELECT COUNT(*) FROM events WHERE parse_error IS NOT NULL").fetchone()[0]
    )
    counts["independent_events"] = int(
        connection.execute(
            "SELECT COUNT(*) FROM events WHERE canonical_event_id IS NULL AND event_type<>'compacted'"
        ).fetchone()[0]
    )
    counts["duplicate_events"] = int(
        connection.execute("SELECT COUNT(*) FROM events WHERE canonical_event_id IS NOT NULL").fetchone()[0]
    )
    active = "FROM sources source JOIN source_revisions revision ON revision.id=source.active_revision_id"
    counts["source_bytes"] = int(
        connection.execute(f"SELECT COALESCE(SUM(revision.size_bytes), 0) {active}").fetchone()[0]
    )
    counts["indexed_bytes"] = int(
        connection.execute(f"SELECT COALESCE(SUM(revision.ingested_offset), 0) {active}").fetchone()[0]
    )
    counts["providers"] = {
        row["provider"]: row["count"]
        for row in connection.execute(
            "SELECT provider, COUNT(*) AS count FROM sessions GROUP BY provider ORDER BY provider"
        )
    }
    counts["source_status"] = {
        row["status"]: row["count"]
        for row in connection.execute(
            f"""
            SELECT revision.status, COUNT(*) AS count {active}
            GROUP BY revision.status ORDER BY revision.status
            """
        )
    }
    counts["projects"] = [
        _row_dict(row)
        for row in connection.execute(
            """
            SELECT COALESCE(project.name, sessions.project, '(unknown)') AS project,
                   COUNT(*) AS sessions, SUM(event_count) AS events
            FROM sessions LEFT JOIN projects project ON project.id=sessions.project_id
            GROUP BY COALESCE(project.name, sessions.project, '(unknown)')
            ORDER BY sessions DESC LIMIT 50
            """
        )
    ]
    counts["date_range"] = _row_dict(
        connection.execute("SELECT MIN(started_at) AS first, MAX(ended_at) AS last FROM sessions").fetchone()
    )
    return counts


def _append_filters(clauses: list[str], parameters: list[Any], filters: SearchFilters) -> None:
    mapping = (
        ("s.provider=?", filters.provider),
        ("(project.project_key=? OR project.name=? OR s.project=?)", filters.project),
        ("contributor.display_name=?", filters.contributor),
        ("(activity.code=? OR activity.title=?)", filters.activity),
        ("COALESCE(activity.classification, 'unclassified')=?", filters.activity_classification),
        ("e.role=?", filters.role),
        ("t.kind=?", filters.kind),
        ("e.timestamp>=?", filters.date_from),
        ("e.timestamp<=?", filters.date_to),
    )
    for clause, value in mapping:
        if not value:
            continue
        clauses.append(clause)
        if clause.count("?") == 3:
            parameters.extend([value, value, value])
        elif clause.count("?") == 2:
            parameters.extend([value, value])
        else:
            parameters.append(value)
    if filters.errors_only:
        clauses.append("t.is_error")


def _row_dict(row: Row) -> dict[str, Any]:
    return dict(row)


def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
