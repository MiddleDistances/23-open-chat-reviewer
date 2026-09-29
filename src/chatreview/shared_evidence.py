"""Immutable, content-addressed timesheet evidence; occurrences remain on intervals."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from chatreview.db import Session


def canonical_members(rows: list[dict[str, Any]]) -> list[tuple[int, str | None]]:
    members: dict[int, str | None] = {}
    for row in rows:
        event_id, episode = int(row["event_id"]), row["episode_key"]
        if event_id in members and members[event_id] != episode:
            raise ValueError(f"Conflicting episode membership for event {event_id}")
        members[event_id] = episode
    return sorted(members.items())


def evidence_fingerprint(members: list[tuple[int, str | None]]) -> str:
    # jsonb array text uses the same separators, Unicode and null representation.
    value = "v1\n" + "\n".join(json.dumps(list(row), ensure_ascii=False) for row in members)
    return "v1:" + hashlib.sha256(value.encode()).hexdigest()


def persist_evidence(connection: Session, rows: list[dict[str, Any]]) -> int:
    members = canonical_members(rows)
    fingerprint = evidence_fingerprint(members)
    row = connection.execute(
        """INSERT INTO timesheet_evidence_sets(fingerprint,member_count) VALUES (?,?)
           ON CONFLICT (fingerprint) DO NOTHING RETURNING id""",
        (fingerprint, len(members)),
    ).fetchone()
    if row is not None:
        set_id = int(row["id"])
        if members:
            connection.executemany(
                """INSERT INTO timesheet_evidence_members(evidence_set_id,event_id,episode_key)
                   VALUES (?,?,?)""",
                [(set_id, event, episode) for event, episode in members],
            )
    else:
        row = connection.execute(
            "SELECT id,member_count FROM timesheet_evidence_sets WHERE fingerprint=?",
            (fingerprint,),
        ).fetchone()
        assert row is not None
        set_id = int(row["id"])
        actual = connection.execute(
            """SELECT event_id,episode_key FROM timesheet_evidence_members
               WHERE evidence_set_id=? ORDER BY event_id""",
            (set_id,),
        ).fetchall()
        if int(row["member_count"]) != len(members) or canonical_members(actual) != members:
            raise ValueError(f"Evidence set {set_id} does not match its fingerprint")
    return set_id


def calculation_fingerprint(connection: Session, timezone_name: str) -> str:
    """Inputs beyond the corpus identity which can change interval attribution."""
    payload: dict[str, Any] = {"timezone": timezone_name}
    for table in (
        "contributor_rules",
        "project_default_activities",
        "occurrence_activity_overrides",
        "activities",
        "project_aliases",
    ):
        # Fixed internal identifiers only; ORDER BY serialized row is deterministic.
        payload[table] = [
            r["value"]
            for r in connection.execute(
                f"SELECT to_jsonb(t)::text AS value FROM {table} t ORDER BY to_jsonb(t)::text"
            ).fetchall()
        ]
    payload["sessions"] = [
        r["value"]
        for r in connection.execute(
            """SELECT jsonb_build_array(id,project_id,contributor_id,parent_session_id,
               provider,external_id,machine_id)::text AS value
           FROM sessions ORDER BY id"""
        ).fetchall()
    ]
    payload["episodes"] = connection.execute(
        "SELECT value FROM schema_meta WHERE key='episode_generation'"
    ).fetchone()
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
