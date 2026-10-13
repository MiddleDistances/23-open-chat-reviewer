"""Durable source checkpoints for bounded session and episode refreshes."""

from __future__ import annotations

import json
from dataclasses import dataclass

from chatreview.db import Session
from chatreview.providers.base import stable_hash


@dataclass(frozen=True)
class SourceChanges:
    """A captured source state, acknowledged only after successful derivation."""

    key: str
    snapshot: str
    session_ids: list[int] | None

    def record(self, connection: Session) -> None:
        """Publish the captured state in the caller's successful transaction."""
        connection.execute(
            "INSERT INTO schema_meta(key,value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (self.key, self.snapshot),
        )


def source_changes(
    connection: Session, key: str, *, canonical_dependencies: bool = False
) -> SourceChanges:
    """Find sessions of changed revisions without reading the event corpus.

    Persist individual source signatures rather than a time watermark so concurrent
    and interrupted writers are revisited. Include historical revisions and parser
    checkpoints. Source discovery timestamps are intentionally excluded.
    """
    rows = connection.execute(
        "SELECT source_id,id,parser_version,ingested_offset,ingested_lines,"
        "aggregate_hash,status,error_count,updated_at FROM source_revisions "
        "ORDER BY source_id,id"
    ).fetchall()
    by_source: dict[str, list[list[str]]] = {}
    for row in rows:
        by_source.setdefault(str(row["source_id"]), []).append([str(value) for value in row.values()])
    current = {key: stable_hash(json.dumps(value)) for key, value in by_source.items()}
    snapshot = json.dumps(current, sort_keys=True)
    row = connection.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    if row is None:
        return SourceChanges(key, snapshot, None)
    previous = json.loads(row["value"])
    # Source removal and explicit archive rebuilds require complete reconciliation.
    if previous.keys() - current.keys():
        return SourceChanges(key, snapshot, None)
    changed = [int(source) for source, signature in current.items() if previous.get(source) != signature]
    ids = []
    if changed:
        ids = [
            int(row["session_id"])
            for row in connection.execute(
                "SELECT DISTINCT session_id FROM session_sources WHERE source_id=ANY(?)",
                (changed,),
            ).fetchall()
        ]
    if canonical_dependencies and ids:
        # A copied provider prefix can change canonical ownership in another
        # source. Include its sessions using the provider-identity index.
        related = connection.execute(
            "SELECT DISTINCT related.session_id FROM events touched "
            "JOIN events related ON related.provider_event_id=touched.provider_event_id "
            "AND related.event_fingerprint=touched.event_fingerprint "
            "WHERE touched.session_id=ANY(?) AND related.session_id IS NOT NULL",
            (ids,),
        ).fetchall()
        ids = sorted(set(ids) | {int(row['session_id']) for row in related})
    return SourceChanges(key, snapshot, ids)
