"""Retrieval-time evidence cards and bounded reads of original archive events.

Formatting and candidate deduplication never alter the archive or infer outcomes.
The CLI/UI search contract remains in ``search``; this module serves agent recall.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from chatreview.db import Session
from chatreview.search import SearchFilters, lexical_search

DISCOVERY_BUDGET = 12_000
CONTEXT_BUDGET = 16_000
SNIPPET_LIMIT = 800
MAX_CANDIDATES = 150


def serialized_size(value: Any) -> int:
    """Count the entire pretty JSON envelope, including escaped Unicode."""
    return len(json.dumps(value, ensure_ascii=True, indent=2, default=str))


def _time(row: dict[str, Any]) -> tuple[str, int]:
    value = row.get("timestamp")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            value = None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(), int(row.get("event_id") or 0)
    return "", int(row.get("event_id") or 0)


def _identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("session_id"), row.get("event_key") or row.get("event_id"),
        row.get("unit_key") or ("unit_index", row.get("unit_index")),
    )


def dedupe_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse exact copies and same-unit prefixes, preserving rank and receipts.

    Compare full text, never snippets. Distinct units within one event and changed
    numeric/code/output content survive. The returned counts describe only rows
    provided by the caller, not the corpus. Complete same-unit copies take priority
    over shorter copies; identical content across events uses source recency.
    """
    groups: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, 1):
        text = row.get("text")
        match = None
        for group in groups:
            old = group["row"]
            same_unit = (
                (row.get("event_key") is not None or row.get("event_id") is not None)
                and (row.get("unit_key") is not None or row.get("unit_index") is not None)
                and _identity(row) == _identity(old)
            )
            same_event = row.get("event_id") == old.get("event_id")
            exact = isinstance(text, str) and text == old.get("text")
            prefix = (
                same_unit and isinstance(text, str) and isinstance(old.get("text"), str)
                and bool(text) and bool(old["text"])
                and (text.startswith(old["text"]) or old["text"].startswith(text))
            )
            comparable = (row.get("role"), row.get("kind"), row.get("provider")) == (
                old.get("role"), old.get("kind"), old.get("provider")
            )
            distinct_unit_in_event = any(
                row.get("event_id") is not None and copy.get("event_id") == row["event_id"]
                and (_identity(copy) != _identity(row) or (
                    row.get("unit_key") is None and row.get("unit_index") is None
                )) for copy in group["copies"]
            )
            if comparable and not distinct_unit_in_event and (
                prefix or (exact and (same_unit or not same_event))
            ):
                match = group
                break
        if match is None:
            groups.append({"row": dict(row), "copies": [dict(row)], "rank": rank})
        else:
            match["copies"].append(dict(row))
            old = match["row"]
            if (
                _identity(row) == _identity(old) and len(text or "") > len(old.get("text") or "")
            ) or (text == old.get("text") and _time(row) > _time(old)):
                match["row"] = dict(row)
    return groups


def _reference(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": row.get("session_id"), "event_id": row.get("event_id"),
        "unit_key": row.get("unit_key"), "observed_at": row.get("timestamp"),
        "raw_record_id": row.get("raw_record_id"), "provenance_hash": row.get("provenance_hash"),
    }


def _clip(value: Any, maximum: int) -> tuple[str, bool]:
    text = "" if value is None else str(value)
    return text[:maximum], len(text) > maximum


def evidence_card(group: dict[str, Any]) -> dict[str, Any]:
    """Produce a verbatim discovery excerpt and an explicit original-event target."""
    row = group["row"]
    # PostgreSQL supplies these two highlight tags; leave other markup untouched.
    snippet = str(row.get("snippet") or row.get("text") or "")
    snippet = snippet.replace("<mark>", "").replace("</mark>", "")
    snippet, clipped = _clip(snippet, SNIPPET_LIMIT)
    source, source_clipped = _clip(row.get("source_path"), 500)
    project, project_clipped = _clip(row.get("project"), 300)
    copies = group["copies"]
    alternate_rows = {}
    for copy in copies:
        if _identity(copy) != _identity(row):
            alternate_rows.setdefault(_identity(copy), copy)
    alternates = [_reference(r) for r in list(alternate_rows.values())[:3]]
    return {
        **_reference(row), "anchor_event_id": row.get("event_id"),
        "relevance_rank": group["rank"],
        "lexical_score": max((r.get("lexical_score") or 0 for r in copies), default=0),
        "provider": row.get("provider"), "project": project,
        "role": row.get("role"), "kind": row.get("kind"),
        "snippet": snippet, "snippet_truncated": clipped,
        "snippet_is_excerpt": row.get("snippet") is not None,
        "source_path": source, "metadata_truncated": source_clipped or project_clipped,
        "source_status": row.get("source_status", "unknown"),
        "duplicates_collapsed": len(copies) - 1,
        "alternate_references": alternates,
        "alternate_references_omitted": max(0, len(alternate_rows) - len(alternates)),
        "full_text_available": True,
        "read_target": {
            "tool": "read_prior_work", "session_id": row.get("session_id"),
            "anchor_event_id": row.get("event_id"), "unit_key": row.get("unit_key"),
        },
    }


def compact_response(
    rows: list[dict[str, Any]], *, query: str, filters: dict[str, Any] | None = None,
    limit: int = 5, candidate_limit: int = MAX_CANDIDATES, budget: int = DISCOVERY_BUDGET,
) -> dict[str, Any]:
    """Group ranked candidates into conversations within a total JSON budget."""
    if budget < 512:
        raise ValueError("response budget must be at least 512 characters")
    limit = min(max(limit, 1), 20)
    groups = dedupe_candidates(rows)
    result: dict[str, Any] = {
        "version": "compact-recall/v1", "query": query, "filters": filters or {},
        "source_mode": "lexical", "candidate_count": len(rows),
        "ordering": "relevance first; recency only selects identical copies",
        "candidate_limit": candidate_limit, "candidate_limit_reached": len(rows) >= candidate_limit,
        "returned_conversations": 0, "returned_anchors": 0,
        "duplicates_collapsed": len(rows) - len(groups),
        "response_truncated": False, "more_results_may_exist": bool(rows),
        "conversations": [],
    }
    # Enormous echoed caller metadata must not defeat even an empty-response budget.
    if serialized_size(result) > budget - 128:
        return {"version": "compact-recall/v1", "error": "metadata_exceeds_budget",
                "response_truncated": True, "conversations": []}
    conversations: dict[Any, dict[str, Any]] = {}
    omitted = False
    for group in groups:
        row = group["row"]
        sid = row.get("session_id")
        if sid is None:
            omitted = True
            continue
        conversation = conversations.get(sid)
        if conversation is None:
            if len(conversations) >= limit:
                omitted = True
                continue
            conversation = {"session_id": sid, "anchors": []}
            conversations[sid] = conversation
            result["conversations"].append(conversation)
        if len(conversation["anchors"]) >= 3:
            omitted = True
            continue
        card = evidence_card(group)
        conversation["anchors"].append(card)
        while serialized_size(result) > budget - 128 and len(card["snippet"]) > 80:
            card["snippet"] = card["snippet"][:len(card["snippet"]) // 2]
            card["snippet_truncated"] = True
            omitted = True
        for field in ("source_path", "project"):
            while serialized_size(result) > budget - 128 and len(card[field]) > 32:
                card[field] = card[field][:len(card[field]) // 2]
                card["metadata_truncated"] = True
                omitted = True
        if serialized_size(result) > budget - 128:
            conversation["anchors"].pop()
            if not conversation["anchors"]:
                result["conversations"].remove(conversation)
                conversations.pop(sid)
            omitted = True
    result["returned_conversations"] = len(result["conversations"])
    result["returned_anchors"] = sum(len(c["anchors"]) for c in result["conversations"])
    result["response_truncated"] = omitted
    if rows and not result["returned_anchors"]:
        result["budget_diagnostic"] = "no_evidence_card_fits"
    return result


def find_prior_work(
    connection: Session, query: str, *, provider: str | None = None,
    project: str | None = None, date_from: str | None = None, date_to: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Read capped lexical candidates and revision-local source completeness."""
    filters = {"provider": provider, "project": project, "date_from": date_from, "date_to": date_to}
    if len(query) > 2000 or any(len(str(v)) > 512 for v in filters.values() if v):
        raise ValueError("query or filter exceeds recall input budget")
    limit = min(max(limit, 1), 20)
    cap = min(MAX_CANDIDATES, limit * 9)
    connection.execute("SET LOCAL statement_timeout = '10s'")
    rows = lexical_search(
        connection, query, filters=SearchFilters(**filters, include_reasoning=False), limit=cap,
    )
    if rows:
        statuses = {
            r["id"]: r["status"] for r in connection.execute(
                """SELECT e.id, r.status FROM events e
                JOIN source_revisions r ON r.id=e.source_revision_id WHERE e.id=ANY(?)""",
                ([r["event_id"] for r in rows],),
            )
        }
        for row in rows:
            row["source_status"] = statuses.get(row["event_id"], "unknown")
    return compact_response(rows, query=query, filters=filters, limit=limit, candidate_limit=cap)


def read_prior_work(
    connection: Session, session_id: int, anchor_event_id: int, *, unit_key: str | None = None,
    before: int = 2, after: int = 2, text_offset: int = 0, budget: int = CONTEXT_BUDGET,
    unit_offset: int = 0,
) -> dict[str, Any]:
    """Read an anchor-first, indexed chronological neighborhood with continuation.

    Text paging applies to the selected anchor unit; omitted units each expose
    their own read target. Neighborhood paging uses the boundary event as anchor.
    No unrestricted raw payload or entire-session scan is performed.
    """
    if text_offset < 0 or unit_offset < 0 or budget < 512:
        raise ValueError("invalid offset or response budget")
    connection.execute("SET LOCAL statement_timeout = '10s'")
    anchor = connection.execute(
        "SELECT id, session_id, timestamp, ordinal FROM events WHERE id=?", (anchor_event_id,),
    ).fetchone()
    if anchor is None or anchor["session_id"] != session_id:
        raise ValueError("anchor_event_id does not belong to session_id")
    before, after = min(max(before, 0), 3), min(max(after, 0), 3)
    # Row comparisons make null timestamps sort first, matching session traces.
    ids: list[int] = []
    for direction, count, order in [("<", before, "DESC"), (">", after, "ASC")]:
        if count:
            neighbors = connection.execute(
                f"""SELECT id FROM events WHERE session_id=? AND
                (COALESCE(timestamp, '-infinity'::timestamptz), ordinal, id)
                {direction} (COALESCE(?::timestamptz, '-infinity'::timestamptz), ?, ?)
                ORDER BY timestamp {order} NULLS {'LAST' if order == 'DESC' else 'FIRST'},
                         ordinal {order}, id {order} LIMIT ?""",
                (session_id, anchor["timestamp"], anchor["ordinal"], anchor_event_id, count),
            ).fetchall()
            ids.extend(r["id"] for r in neighbors)
    ids.append(anchor_event_id)
    # Select bounded text in SQL; even giant tool records need not enter Python.
    rows = connection.execute(
        """SELECT e.id AS event_id, e.timestamp, e.ordinal, e.role, e.subtype,
        e.raw_record_id, rr.payload_hash AS provenance_hash, s.path AS source_path,
        r.status AS source_status, t.unit_key, t.kind, t.label, t.unit_index,
        c.char_count AS full_text_chars,
        substring(c.text FROM (CASE WHEN e.id=? AND (?::text IS NULL OR t.unit_key=?)
                    THEN ? ELSE 0 END) + 1 FOR 16001) AS text
        FROM events e JOIN sources s ON s.id=e.source_id
        JOIN source_revisions r ON r.id=e.source_revision_id
        JOIN raw_records rr ON rr.id=e.raw_record_id
        LEFT JOIN LATERAL (
            SELECT * FROM text_units u WHERE u.event_id=e.id
            AND (e.id!=? OR ?::text IS NULL OR u.unit_key=?)
            ORDER BY u.unit_index LIMIT (CASE WHEN e.id=? THEN 3 ELSE 1 END)
            OFFSET (CASE WHEN e.id=? AND ?::text IS NULL THEN ? ELSE 0 END)
        ) t ON true LEFT JOIN contents c ON c.id=t.content_id
        WHERE e.id=ANY(?) ORDER BY e.timestamp NULLS FIRST, e.ordinal, e.id, t.unit_index""",
        (anchor_event_id, unit_key, unit_key, text_offset,
         anchor_event_id, unit_key, unit_key, anchor_event_id,
         anchor_event_id, unit_key, unit_offset, ids),
    ).fetchall()
    if unit_key and not any(r["event_id"] == anchor_event_id and r["unit_key"] == unit_key for r in rows):
        raise ValueError("unit_key does not belong to anchor_event_id")
    selected = [r for r in rows if r["event_id"] == anchor_event_id and r["unit_key"]]
    if not selected and unit_offset:
        raise ValueError("unit_offset exceeds anchor units")
    if any(text_offset > (r["full_text_chars"] or 0) for r in selected):
        raise ValueError("text_offset exceeds selected unit text")
    counts = connection.execute(
        "SELECT event_id, COUNT(*) AS count FROM text_units WHERE event_id=ANY(?) GROUP BY event_id",
        (ids,),
    ).fetchall()
    unit_pages = []
    for count in counts:
        eid = count["event_id"]
        returned = sum(r["event_id"] == eid and r["unit_key"] is not None for r in rows)
        skip = unit_offset if eid == anchor_event_id and unit_key is None else 0
        if count["count"] > returned + skip and not (eid == anchor_event_id and unit_key):
            unit_pages.append({"session_id": session_id, "anchor_event_id": eid,
                               "before": 0, "after": 0, "unit_offset": skip + returned})
    result: dict[str, Any] = {
        "version": "prior-work-context/v1", "session_id": session_id,
        "anchor_event_id": anchor_event_id, "response_truncated": False,
        "events": [], "omitted_units": [], "unit_continuations": unit_pages,
        "neighborhood": {"before": before, "after": after,
                         "continuation": "Use a boundary event as the next anchor."},
    }
    # Reserve space for explicit omitted-unit targets before prioritizing anchor text.
    ordered = sorted(rows, key=lambda r: (
        r["event_id"] != anchor_event_id,
        unit_key is not None and r["unit_key"] != unit_key,
        r["unit_index"] or 0,
    ))
    for row in ordered:
        item = dict(row)
        item.pop("ordinal")
        item.pop("unit_index")
        offset = text_offset if row["event_id"] == anchor_event_id and (
            unit_key is None or row["unit_key"] == unit_key
        ) else 0
        item["text_offset"] = offset
        item["source_path"], path_clipped = _clip(item["source_path"], 500)
        item["metadata_truncated"] = path_clipped
        item["text"] = item["text"] or ""
        item["text_truncated"] = offset + len(item["text"]) < (item["full_text_chars"] or 0)
        item["next_read"] = None
        result["events"].append(item)
        # Budget omissions need only bounded IDs, not arbitrary provider metadata.
        reserve = 400 * len(rows) + 200
        while serialized_size(result) > budget - reserve and item["text"]:
            item["text"] = item["text"][:len(item["text"]) // 2]
            item["text_truncated"] = True
        target = {"session_id": session_id, "anchor_event_id": row["event_id"],
                  "unit_key": row["unit_key"], "before": 0, "after": 0}
        if serialized_size(result) > budget - reserve:
            result["events"].pop()
            result["omitted_units"].append(target)
        elif item["text_truncated"]:
            item["next_read"] = {**target, "text_offset": offset + len(item["text"])}
        result["response_truncated"] |= item["text_truncated"]
    result["response_truncated"] |= bool(result["omitted_units"] or unit_pages)
    # Final contract protects against large identifiers, dates, or unusual unit counts.
    while serialized_size(result) > budget and result["events"]:
        removed = result["events"].pop()
        result["omitted_units"].append({"session_id": session_id,
            "anchor_event_id": removed["event_id"], "unit_key": removed["unit_key"],
            "before": 0, "after": 0})
        result["response_truncated"] = True
    if serialized_size(result) > budget or not any(
        e["event_id"] == anchor_event_id for e in result["events"]
    ):
        return {"version": "prior-work-context/v1", "session_id": session_id,
                "anchor_event_id": anchor_event_id, "response_truncated": True,
                "error": "no_context_fits_budget", "events": []}
    # Restore chronological ordering after allocating the anchor first.
    positions = {(r["event_id"], r["unit_key"]): i for i, r in enumerate(rows)}
    result["events"].sort(key=lambda r: positions[(r["event_id"], r["unit_key"])])
    return result
