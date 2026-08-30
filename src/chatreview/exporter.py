from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Literal

from chatreview.db import Session
from chatreview.search import SearchFilters, lexical_search, session_events

ExportFormat = Literal["markdown", "jsonl", "csv"]


def collect_evidence(
    connection: Session,
    *,
    query: str | None = None,
    session_id: int | None = None,
    label: str | None = None,
    filters: SearchFilters | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    if query:
        return lexical_search(connection, query, filters=filters, limit=min(limit, 500))
    if session_id is not None:
        events = session_events(connection, session_id, limit=min(limit, 5000), include_empty=False)
        rows = []
        for event in events:
            for unit in event.pop("units", []):
                rows.append({**event, **unit})
        return rows
    if label:
        rows = connection.execute(
            """
            SELECT a.target_type, a.target_key, a.note, a.review_state, l.name AS label,
                   a.created_at, a.updated_at
            FROM annotations a JOIN labels l ON l.id=a.label_id
            WHERE l.name=? ORDER BY a.updated_at DESC LIMIT ?
            """,
            (label, limit),
        ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]
    raise ValueError("an export requires query, session_id, or label")


def render_evidence(records: list[dict[str, Any]], format: ExportFormat) -> str:
    if format == "jsonl":
        return "".join(json.dumps(item, ensure_ascii=False, default=str) + "\n" for item in records)
    if format == "csv":
        if not records:
            return ""
        fields = sorted({key for record in records for key in record})
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in record.items()
                }
            )
        return output.getvalue()
    lines = ["# ChatReviewer Evidence Export", ""]
    for index, record in enumerate(records, start=1):
        title = record.get("kind") or record.get("event_type") or record.get("target_type") or "record"
        lines.extend([f"## {index}. {title}", ""])
        metadata = {
            key: record.get(key)
            for key in (
                "provider",
                "project",
                "session_external_id",
                "session_id",
                "timestamp",
                "role",
                "source_path",
                "line_no",
                "label",
                "review_state",
            )
            if record.get(key) is not None
        }
        for key, value in metadata.items():
            lines.append(f"- **{key.replace('_', ' ').title()}**: `{value}`")
        text = record.get("text") or record.get("snippet") or record.get("note")
        if text:
            lines.extend(["", str(text).replace("<mark>", "**").replace("</mark>", "**"), ""])
    return "\n".join(lines).rstrip() + "\n"


def write_export(path: Path, records: list[dict[str, Any]], format: ExportFormat) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_evidence(records, format), encoding="utf-8")
    return path
