"""Persist provider-neutral usage and backfill retained archives without source reads."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import orjson

from chatreview.db import Session, database
from chatreview.providers.claude import TOKEN_USAGE_VERSION, extract_token_usage
from chatreview.types import TokenUsage


def persist_usage(connection: Session, items: list[tuple[str, TokenUsage | None]]) -> None:
    """Resolve event keys in one set-based insert within the ingestion transaction."""
    if not items:
        return
    payload = [{"event_key": key, "usage": asdict(usage) if usage else None} for key, usage in items]
    connection.execute(
        """INSERT INTO event_token_usage(event_id, extraction_version, status, usage_json)
        SELECT e.id, ?, CASE WHEN x.usage IS NULL THEN 'missing' ELSE 'available' END, x.usage
        FROM jsonb_to_recordset(?::jsonb) AS x(event_key text, usage jsonb)
        JOIN events e ON e.event_key=x.event_key
        ON CONFLICT(event_id) DO UPDATE SET extraction_version=excluded.extraction_version,
            status=excluded.status, usage_json=excluded.usage_json""",
        (TOKEN_USAGE_VERSION, orjson.dumps(payload).decode()),
    )


def backfill_usage(database_url: str, *, batch_size: int = 1000, force: bool = False) -> dict[str, int]:
    """Resume by extraction version, committing bounded batches under one archive lock.

    Missing retained payloads are recorded as unavailable, not zero usage. A forced
    rebuild rechecks them and applies parser corrections without rebuilding events.
    """
    counts = {"processed": 0, "available": 0, "missing": 0, "unavailable": 0}
    with database(database_url) as connection, connection.advisory_lock("token-usage-backfill"):
        after = 0
        while True:
            rows = connection.execute(
                """SELECT e.id, rp.payload FROM events e JOIN sources s ON s.id=e.source_id
                JOIN raw_records rr ON rr.id=e.raw_record_id
                LEFT JOIN raw_payloads rp ON rp.payload_hash=rr.payload_hash
                LEFT JOIN event_token_usage u ON u.event_id=e.id
                WHERE s.provider='claude' AND e.role='assistant' AND e.id>?
                  AND (? OR u.event_id IS NULL OR u.extraction_version<>?)
                ORDER BY e.id LIMIT ?""",
                (after, force, TOKEN_USAGE_VERSION, batch_size),
            ).fetchall()
            if not rows:
                break
            items: list[tuple[Any, ...]] = []
            for row in rows:
                usage = None
                status = "unavailable" if row["payload"] is None else "missing"
                if row["payload"] is not None:
                    try:
                        data = orjson.loads(bytes(row["payload"]))
                        usage = extract_token_usage(data) if isinstance(data, dict) else None
                    except (ValueError, TypeError):
                        pass
                if usage:
                    status = "available"
                items.append(
                    (
                        row["id"],
                        TOKEN_USAGE_VERSION,
                        status,
                        orjson.dumps(asdict(usage)).decode() if usage else None,
                    )
                )
                counts[status] += 1
                counts["processed"] += 1
            connection.executemany(
                """INSERT INTO event_token_usage(event_id,extraction_version,status,usage_json)
                VALUES (?,?,?,?::jsonb) ON CONFLICT(event_id) DO UPDATE SET
                extraction_version=excluded.extraction_version,status=excluded.status,
                usage_json=excluded.usage_json""",
                items,
            )
            connection.commit()
            after = rows[-1]["id"]
    return counts
