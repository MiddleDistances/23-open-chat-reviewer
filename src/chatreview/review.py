from __future__ import annotations

from typing import Any, Literal

from chatreview.config import Settings
from chatreview.db import Session
from chatreview.search import SearchFilters, lexical_search
from chatreview.semantic import SemanticSearchService

ReviewMode = Literal["lexical", "semantic", "hybrid"]


def build_review_queue(
    connection: Session,
    settings: Settings,
    *,
    query: str | None = None,
    mode: ReviewMode = "lexical",
    filters: SearchFilters | None = None,
    limit: int = 50,
    unreviewed_only: bool = True,
) -> list[dict[str, Any]]:
    """Build a bounded queue whose targets remain stable across UI and CLI review."""
    filters = filters or SearchFilters()
    candidates: list[dict[str, Any]] = []
    if query:
        if mode in {"lexical", "hybrid"}:
            for result in lexical_search(connection, query, filters=filters, limit=limit * 3):
                candidates.append(
                    {
                        "target_type": "event",
                        "target_key": result["event_key"],
                        "event_id": result["event_id"],
                        "session_id": result["session_id"],
                        "provider": result["provider"],
                        "project": result["project"],
                        "timestamp": result["timestamp"],
                        "heading": f"{result['event_type']} / {result['kind']}",
                        "preview": result["text"][:4_000],
                        "provenance": f"{result['source_path']}:{result['line_no']}",
                    }
                )
        if mode in {"semantic", "hybrid"}:
            for result in SemanticSearchService(settings).search(
                connection, query, filters=filters, limit=limit * 3
            ):
                candidates.append(
                    {
                        "target_type": "window",
                        "target_key": result["window_key"],
                        "event_id": result["first_event_id"],
                        "session_id": result["session_id"],
                        "provider": result["provider"],
                        "project": result["project"],
                        "timestamp": result["started_at"],
                        "heading": f"semantic window · {result['semantic_score']:.3f}",
                        "preview": result["snippet"][:4_000],
                        "provenance": (f"events {result['first_event_id']}–{result['last_event_id']}"),
                    }
                )
    else:
        candidates.extend(_recent_session_candidates(connection, filters, limit * 3))

    queue = []
    seen: set[tuple[str, str]] = set()
    for item in candidates:
        identity = (item["target_type"], item["target_key"])
        if identity in seen:
            continue
        seen.add(identity)
        annotations = annotations_for(connection, *identity)
        if unreviewed_only and any(row["review_state"] == "reviewed" for row in annotations):
            continue
        item["annotations"] = annotations
        queue.append(item)
        if len(queue) >= limit:
            break
    return queue


def annotations_for(
    connection: Session, target_type: str, target_key: str
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT a.id, a.target_type, a.target_key, a.note, a.review_state,
               a.created_at, a.updated_at, l.name AS label, l.color
        FROM annotations a LEFT JOIN labels l ON l.id=a.label_id
        WHERE a.target_type=? AND a.target_key=? ORDER BY a.updated_at
        """,
        (target_type, target_key),
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def save_review(
    connection: Session,
    *,
    target_type: str,
    target_key: str,
    label: str | None,
    note: str | None,
    review_state: str = "reviewed",
) -> dict[str, Any]:
    if target_type not in {"session", "event", "window", "episode"}:
        raise ValueError("target_type must be session, event, window, or episode")
    if review_state not in {"unreviewed", "reviewing", "reviewed"}:
        raise ValueError("review_state must be unreviewed, reviewing, or reviewed")
    label_id = None
    if label:
        row = connection.execute("SELECT id FROM labels WHERE name=?", (label,)).fetchone()
        if row is None:
            raise ValueError(f"unknown label: {label}")
        label_id = int(row["id"])
    if label_id is None:
        existing = connection.execute(
            """
            SELECT id FROM annotations
            WHERE target_type=? AND target_key=? AND label_id IS NULL
            ORDER BY id LIMIT 1
            """,
            (target_type, target_key),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE annotations SET note=?, review_state=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (note, review_state, existing["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO annotations(target_type, target_key, label_id, note, review_state)
                VALUES (?, ?, NULL, ?, ?)
                """,
                (target_type, target_key, note, review_state),
            )
    else:
        connection.execute(
            """
            INSERT INTO annotations(target_type, target_key, label_id, note, review_state)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(target_type, target_key, label_id) DO UPDATE SET
                note=excluded.note, review_state=excluded.review_state,
                updated_at=CURRENT_TIMESTAMP
            """,
            (target_type, target_key, label_id, note, review_state),
        )
    connection.commit()
    rows = annotations_for(connection, target_type, target_key)
    matching = [row for row in rows if row["label"] == label]
    return matching[-1] if matching else rows[-1]


def available_labels(connection: Session) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT l.name, l.color, l.description, COUNT(a.id) AS annotation_count
        FROM labels l LEFT JOIN annotations a ON a.label_id=l.id
        GROUP BY l.id ORDER BY l.name
        """
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _recent_session_candidates(
    connection: Session, filters: SearchFilters, limit: int
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    parameters: list[Any] = []
    if filters.provider:
        clauses.append("s.provider=?")
        parameters.append(filters.provider)
    if filters.project:
        clauses.append("s.project=?")
        parameters.append(filters.project)
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT s.id AS session_id, s.session_key, s.provider, s.project,
               s.started_at, s.ended_at, s.event_count,
               COALESCE((
                   SELECT substr(c.text, 1, 4000)
                   FROM events e JOIN text_units t ON t.event_id=e.id
                   JOIN contents c ON c.id=t.content_id
                   WHERE e.session_id=s.id AND t.kind IN (
                       'user-message', 'assistant-message', 'agent-message',
                       'last-prompt', 'context-summary', 'compaction-summary'
                   )
                   ORDER BY COALESCE(e.timestamp, '') DESC, e.ordinal DESC LIMIT 1
               ), '') AS preview
        FROM sessions s WHERE {" AND ".join(clauses)}
        ORDER BY COALESCE(s.ended_at, s.started_at) DESC LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [
        {
            "target_type": "session",
            "target_key": row["session_key"],
            "event_id": None,
            "session_id": row["session_id"],
            "provider": row["provider"],
            "project": row["project"],
            "timestamp": row["ended_at"] or row["started_at"],
            "heading": f"session · {row['event_count']:,} events",
            "preview": row["preview"],
            "provenance": f"session {row['session_id']}",
        }
        for row in rows
    ]
