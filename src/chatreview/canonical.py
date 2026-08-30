from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import orjson

from chatreview.db import Session
from chatreview.providers.base import stable_hash
from chatreview.types import ParsedRecord

ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class CanonicalSummary:
    fingerprinted_events: int
    duplicate_groups: int
    duplicate_events: int


def parsed_event_fingerprint(provider: str, parsed: ParsedRecord) -> str:
    """Return a stable semantic identity for one provider event.

    Provider UUIDs/call IDs identify a logical event, while this fingerprint prevents
    accidental collapse when a provider reuses an identifier for distinct payloads.
    Source paths, timestamps, and mutable metadata are intentionally excluded so shared
    fork prefixes can converge on one canonical event.
    """
    units = [
        [fragment.kind, fragment.label, bool(fragment.is_error), stable_hash(fragment.text)]
        for fragment in parsed.fragments
    ]
    payload = [provider, parsed.event_type, parsed.subtype, parsed.role, units]
    return stable_hash(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))


def assign_canonical_for_event(
    connection: Session,
    *,
    event_id: int,
    provider_event_id: str | None,
    event_fingerprint: str | None,
) -> int | None:
    """Link one newly ingested event to the earliest matching provider event."""
    if not provider_event_id or not event_fingerprint:
        return None
    row = connection.execute(
        """
        SELECT MIN(id) AS canonical_id
        FROM events
        WHERE provider_event_id=? AND event_fingerprint=?
        """,
        (provider_event_id, event_fingerprint),
    ).fetchone()
    if row is None or row["canonical_id"] is None:
        return None
    canonical_id = int(row["canonical_id"])
    connection.execute(
        """
        UPDATE events
        SET canonical_event_id=CASE WHEN id=? THEN NULL ELSE ? END
        WHERE provider_event_id=? AND event_fingerprint=?
        """,
        (canonical_id, canonical_id, provider_event_id, event_fingerprint),
    )
    return canonical_id if event_id != canonical_id else None


def reconcile_canonical_events(
    connection: Session,
    *,
    progress: ProgressCallback | None = None,
    batch_size: int = 5_000,
) -> CanonicalSummary:
    """Incrementally fingerprint and canonicalize copied provider events.

    Ingestion canonicalizes every new batch. This pass only repairs legacy rows
    that are still missing fingerprints and then reports the durable duplicate
    links; it never clears and rewrites the complete events table.
    """
    report = progress or (lambda _message: None)
    fingerprinted = _backfill_event_fingerprints(
        connection,
        progress=report,
        batch_size=max(100, batch_size),
    )
    report("Checking durable provider-event identities")
    row = connection.execute(
        """
        SELECT COUNT(DISTINCT canonical_event_id) AS duplicate_groups,
               COUNT(*) AS duplicate_events
        FROM events
        WHERE canonical_event_id IS NOT NULL
        """
    ).fetchone()
    connection.commit()
    return CanonicalSummary(
        fingerprinted_events=fingerprinted,
        duplicate_groups=int(row["duplicate_groups"]),
        duplicate_events=int(row["duplicate_events"]),
    )


def _backfill_event_fingerprints(
    connection: Session,
    *,
    progress: ProgressCallback,
    batch_size: int,
) -> int:
    last_id = 0
    processed = 0
    while True:
        events = connection.execute(
            """
            SELECT e.id, source.provider, e.event_type, e.subtype, e.role
            FROM events e
            JOIN sources source ON source.id=e.source_id
            WHERE e.id>? AND e.provider_event_id IS NOT NULL
              AND e.event_fingerprint IS NULL
            ORDER BY e.id
            LIMIT ?
            """,
            (last_id, batch_size),
        ).fetchall()
        if not events:
            break
        event_ids = [int(row["id"]) for row in events]
        placeholders = ",".join("?" for _ in event_ids)
        units_by_event: dict[int, list[list[Any]]] = {event_id: [] for event_id in event_ids}
        unit_rows = connection.execute(
            f"""
            SELECT t.event_id, t.unit_index, t.kind, t.label, t.is_error, c.content_hash
            FROM text_units t
            JOIN contents c ON c.id=t.content_id
            WHERE t.event_id IN ({placeholders})
            ORDER BY t.event_id, t.unit_index
            """,
            event_ids,
        ).fetchall()
        for unit in unit_rows:
            units_by_event[int(unit["event_id"])].append(
                [unit["kind"], unit["label"], bool(unit["is_error"]), unit["content_hash"]]
            )
        updates = []
        for event in events:
            event_id = int(event["id"])
            payload = [
                event["provider"],
                event["event_type"],
                event["subtype"],
                event["role"],
                units_by_event[event_id],
            ]
            updates.append(
                (stable_hash(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)), event_id)
            )
        connection.executemany(
            "UPDATE events SET event_fingerprint=? WHERE id=?",
            updates,
        )
        _canonicalize_fingerprint_groups(connection, event_ids)
        connection.commit()
        processed += len(events)
        last_id = event_ids[-1]
        progress(f"  fingerprinted {processed:,} provider events")
    return processed


def _canonicalize_fingerprint_groups(connection: Session, event_ids: list[int]) -> None:
    """Repair only identity groups touched by one fingerprint backfill batch."""

    if not event_ids:
        return
    connection.execute(
        """
        WITH affected AS (
            SELECT DISTINCT provider_event_id, event_fingerprint
            FROM events
            WHERE id=ANY(?)
              AND provider_event_id IS NOT NULL
              AND event_fingerprint IS NOT NULL
        ), canonical AS (
            SELECT event.provider_event_id, event.event_fingerprint,
                   MIN(event.id) AS canonical_id
            FROM events event
            JOIN affected
              ON affected.provider_event_id=event.provider_event_id
             AND affected.event_fingerprint=event.event_fingerprint
            GROUP BY event.provider_event_id, event.event_fingerprint
        )
        UPDATE events target
        SET canonical_event_id=CASE
            WHEN target.id=canonical.canonical_id THEN NULL
            ELSE canonical.canonical_id
        END
        FROM canonical
        WHERE target.provider_event_id=canonical.provider_event_id
          AND target.event_fingerprint=canonical.event_fingerprint
          AND target.canonical_event_id IS DISTINCT FROM CASE
              WHEN target.id=canonical.canonical_id THEN NULL
              ELSE canonical.canonical_id
          END
        """,
        (event_ids,),
    )
