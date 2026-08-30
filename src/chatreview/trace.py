from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import PurePath
from typing import Any

from chatreview.db import Row, Session
from chatreview.providers.base import stable_hash

CORRECTION_PATTERN = re.compile(
    r"(?i)\b(?:still (?:broken|failing|wrong|not)|again|not fixed|did not work|didn't work|"
    r"you (?:missed|ignored|forgot)|incorrect|wrong|not what i (?:asked|meant|wanted)|regress(?:ed|ion)?)\b"
)
SPACE_PATTERN = re.compile(r"\s+")
SHELL_PREFIX = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=[^ ]+\s+|sudo\s+|env\s+)+")
SCRIPT_ENVELOPE = re.compile(r"(?is)^script (?:completed|failed)\s+wall time .*?\s+output:\s*")
SUCCESSFUL_OUTPUT = re.compile(r"(?im)^(?:exit code:\s*0\b|process exited with code 0\b|script completed\b)")

DIRECT_TOOL_ACTIONS = {
    "apply_patch": ("edit", "edit:patch"),
    "edit": ("edit", "edit:file"),
    "write": ("edit", "edit:file"),
    "read": ("inspect", "inspect:file"),
    "view_image": ("inspect", "inspect:image"),
    "glob": ("search", "search:files"),
    "grep": ("search", "search:text"),
    "websearch": ("research", "research:web-search"),
    "webfetch": ("research", "research:web-fetch"),
    "image_query": ("research", "research:image-search"),
    "spawn_agent": ("delegate", "delegate:spawn"),
    "send_message": ("delegate", "delegate:message"),
    "followup_task": ("delegate", "delegate:follow-up"),
    "wait_agent": ("monitor", "monitor:agent"),
    "close_agent": ("monitor", "monitor:agent-close"),
    "write_stdin": ("monitor", "monitor:process"),
    "wait": ("monitor", "monitor:process"),
    "update_plan": ("plan", "plan:update"),
    "taskcreate": ("plan", "plan:create-task"),
    "taskupdate": ("plan", "plan:update-task"),
}


def build_session_trace(
    connection: Session,
    session_id: int,
    *,
    occurrence_limit: int = 500,
    run_limit: int = 120,
) -> dict[str, Any] | None:
    """Project one chat into a bounded, evidence-linked chronological trace."""
    session = connection.execute(
        """
        SELECT id, session_key, provider, external_id, project, cwd, started_at,
               ended_at, title, event_count, text_unit_count
        FROM sessions WHERE id=?
        """,
        (session_id,),
    ).fetchone()
    if session is None:
        return None

    occurrence_limit = min(max(occurrence_limit, 1), 500)
    run_limit = min(max(run_limit, 10), 500)
    total_row = connection.execute(
        "SELECT COUNT(*) AS count FROM episodes WHERE session_id=?",
        (session_id,),
    ).fetchone()
    total_occurrences = int(total_row["count"] if total_row else 0)
    episode_rows = connection.execute(
        """
        SELECT ep.id, ep.episode_key, ep.sequence_no, ep.started_at, ep.ended_at,
               ep.active_seconds, ep.event_count, ep.attempt_count, ep.error_count,
               ep.evidence_state, ep.first_event_id, ep.last_event_id,
               substr(g.text, 1, 1000) AS context,
               substr(o.text, 1, 500) AS outcome
        FROM episodes ep
        LEFT JOIN contents g ON g.id=ep.goal_content_id
        LEFT JOIN contents o ON o.id=ep.outcome_content_id
        WHERE ep.session_id=?
        ORDER BY ep.sequence_no, ep.id
        LIMIT ?
        """,
        (session_id, occurrence_limit),
    ).fetchall()
    if not episode_rows:
        return {
            "session": _row(session),
            "summary": _empty_summary(),
            "occurrences": [],
            "top_transitions": [],
            "truncated": False,
            "total_occurrences": 0,
            "method_note": _method_note(),
        }

    episode_ids = [int(row["id"]) for row in episode_rows]
    fingerprints = _fingerprints(connection, episode_ids)
    units = _trace_units(connection, episode_ids)
    by_episode_units: defaultdict[int, list[Row]] = defaultdict(list)
    for row in units:
        by_episode_units[int(row["episode_id"])].append(row)

    occurrences = []
    action_counts: Counter[str] = Counter()
    transition_counts: Counter[tuple[str, str]] = Counter()
    transition_support: Counter[tuple[str, str]] = Counter()
    correction_count = 0
    tool_call_count = 0

    for row in episode_rows:
        episode_id = int(row["id"])
        episode_fingerprints = fingerprints.get(episode_id, {})
        calls = _calls(by_episode_units.get(episode_id, []))
        runs = _collapse_calls(calls)
        visible_runs = runs[:run_limit]
        hidden_runs = runs[run_limit:]
        hidden_calls = sum(int(run["count"]) for run in hidden_runs)
        context = _tidy(row["context"] or "", 500)
        correction = bool(context and CORRECTION_PATTERN.search(context))
        correction_count += int(correction)
        tool_call_count += len(calls)
        action_counts.update(str(call["action"]) for call in calls)
        seen_transitions: set[tuple[str, str]] = set()
        for left, right in zip(calls, calls[1:], strict=False):
            transition = (str(left["operation"]), str(right["operation"]))
            transition_counts[transition] += 1
            seen_transitions.add(transition)
        transition_support.update(seen_transitions)

        signature = _signature(row, episode_fingerprints, calls, correction=correction)
        occurrences.append(
            {
                "id": episode_id,
                "episode_key": row["episode_key"],
                "sequence_no": row["sequence_no"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "active_seconds": row["active_seconds"],
                "event_count": row["event_count"],
                "tool_call_count": len(calls),
                "derived_attempt_count": row["attempt_count"],
                "error_count": row["error_count"],
                "evidence_state": row["evidence_state"],
                "first_event_id": row["first_event_id"],
                "last_event_id": row["last_event_id"],
                "context": context or None,
                "outcome": _tidy(row["outcome"] or "", 500) or None,
                "correction": correction,
                "signature": signature,
                "call_runs": visible_runs,
                "hidden_run_count": len(hidden_runs),
                "hidden_call_count": hidden_calls,
            }
        )

    summary = {
        "occurrences": total_occurrences,
        "visible_occurrences": len(occurrences),
        "tool_calls": tool_call_count,
        "error_occurrences": sum(int(row["error_count"] or 0) > 0 for row in episode_rows),
        "corrections": correction_count,
        "discussion_occurrences": sum(row["evidence_state"] == "discussion" for row in episode_rows),
        "active_seconds": sum(float(row["active_seconds"] or 0) for row in episode_rows),
        "actions": [{"action": action, "count": count} for action, count in action_counts.most_common()],
    }
    top_transitions = [
        {
            "from": left,
            "to": right,
            "count": count,
            "occurrence_support": transition_support[(left, right)],
        }
        for (left, right), count in transition_counts.most_common(12)
    ]
    return {
        "session": _row(session),
        "summary": summary,
        "occurrences": occurrences,
        "top_transitions": top_transitions,
        "truncated": total_occurrences > len(occurrences),
        "total_occurrences": total_occurrences,
        "method_note": _method_note(),
    }


def normalize_call(tool_name: str | None, value: str | None) -> tuple[str, str]:
    """Map provider-specific tool calls onto a compact, stable action vocabulary."""
    name = (tool_name or "tool").strip().lower()
    compact_name = name.replace("-", "_")
    if compact_name in DIRECT_TOOL_ACTIONS:
        return DIRECT_TOOL_ACTIONS[compact_name]
    if compact_name == "exec":
        return _normalize_exec_wrapper(value or "")
    if compact_name in {"exec_command", "shell", "shell_command", "bash"}:
        return _normalize_shell(_command_value(value))
    if "search" in compact_name:
        return "search", f"search:{compact_name}"
    if "read" in compact_name or "inspect" in compact_name:
        return "inspect", f"inspect:{compact_name}"
    if "edit" in compact_name or "patch" in compact_name or "write" in compact_name:
        return "edit", f"edit:{compact_name}"
    if "browser" in compact_name:
        return "research", f"research:{compact_name}"
    return "other", f"tool:{compact_name}"


def _fingerprints(
    connection: Session,
    episode_ids: list[int],
) -> dict[int, dict[str, list[str]]]:
    placeholders = ",".join("?" for _ in episode_ids)
    rows = connection.execute(
        f"""
        SELECT episode_id, kind, value
        FROM episode_fingerprints
        WHERE episode_id IN ({placeholders})
          AND kind IN ('error-signature', 'path', 'command', 'tool')
        ORDER BY episode_id, kind, value
        """,
        episode_ids,
    ).fetchall()
    result: defaultdict[int, defaultdict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        bucket = result[int(row["episode_id"])][str(row["kind"])]
        if len(bucket) < 8:
            bucket.append(str(row["value"]))
    return {episode_id: dict(kinds) for episode_id, kinds in result.items()}


def _trace_units(connection: Session, episode_ids: list[int]) -> list[Row]:
    placeholders = ",".join("?" for _ in episode_ids)
    # The unique event/unit index anchors this lookup on selected episode events
    # instead of scanning every tool unit in the corpus.
    return connection.execute(
        f"""
        SELECT ee.episode_id, ee.position, e.id AS event_id, e.timestamp,
               t.unit_index, t.kind, t.label, t.is_error,
               CASE WHEN t.kind IN ('tool-input', 'tool-output', 'error')
                    THEN substr(c.text, 1, 4000) ELSE '' END AS text,
               EXISTS(
                   SELECT 1 FROM artifacts a
                   WHERE a.event_id=e.id AND a.kind='error-signature'
               ) AS has_error_artifact
        FROM episode_events ee
        JOIN events e ON e.id=ee.event_id
        JOIN text_units t ON t.event_id=e.id
        JOIN contents c ON c.id=t.content_id
        WHERE ee.episode_id IN ({placeholders})
          AND t.kind IN ('tool-input', 'tool-output', 'error')
        ORDER BY ee.episode_id, ee.position, t.unit_index
        """,
        episode_ids,
    ).fetchall()


def _calls(rows: list[Row]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    pending: list[int] = []
    for row in rows:
        kind = str(row["kind"])
        if kind == "tool-input":
            action, operation = normalize_call(row["label"], row["text"])
            calls.append(
                {
                    "action": action,
                    "operation": operation,
                    "outcome": "unknown",
                    "first_event_id": int(row["event_id"]),
                    "last_event_id": int(row["event_id"]),
                    "started_at": row["timestamp"],
                    "ended_at": row["timestamp"],
                }
            )
            pending.append(len(calls) - 1)
        elif pending:
            call_index = pending.pop(0)
            call = calls[call_index]
            call["last_event_id"] = int(row["event_id"])
            call["ended_at"] = row["timestamp"]
            observed_error = bool(row["is_error"] or kind == "error") or bool(
                row["has_error_artifact"] and not SUCCESSFUL_OUTPUT.search(str(row["text"]))
            )
            call["outcome"] = "error" if observed_error else "result"
    return calls


def _collapse_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for call in calls:
        if runs and all(runs[-1][key] == call[key] for key in ("action", "operation", "outcome")):
            runs[-1]["count"] += 1
            runs[-1]["last_event_id"] = call["last_event_id"]
            runs[-1]["ended_at"] = call["ended_at"]
            continue
        runs.append({**call, "count": 1})
    return runs


def _signature(
    episode: Row,
    fingerprints: dict[str, list[str]],
    calls: list[dict[str, Any]],
    *,
    correction: bool,
) -> dict[str, Any]:
    errors = sorted(
        (_tidy(_error_text(value), 180) for value in fingerprints.get("error-signature", [])),
        key=_error_score,
        reverse=True,
    )[:3]
    entities = _entity_names(fingerprints.get("path", []))
    operations = list(dict.fromkeys(str(call["operation"]) for call in calls))[:6]
    context = _tidy(episode["context"] or "", 220)
    if errors:
        title = f"Observed error: {errors[0]}"
        basis = "observed-error"
    elif entities:
        title = f"Work involving {', '.join(entities[:2])}"
        basis = "affected-entity"
    elif operations:
        title = f"Call sequence led by {operations[0]}"
        basis = "normalised-operation"
    elif context:
        title = context
        basis = "conversation-context"
    else:
        title = f"Occurrence {int(episode['sequence_no']) + 1}"
        basis = "sequence"
    signature_material = "\0".join([*errors, *entities, *operations]) or str(episode["id"])
    return {
        "key": stable_hash(signature_material),
        "title": _tidy(title, 220),
        "basis": basis,
        "errors": errors,
        "entities": entities,
        "operations": operations,
        "correction": correction,
        "provisional": True,
    }


def _entity_names(paths: list[str]) -> list[str]:
    names = []
    for value in paths:
        name = PurePath(value).name or value
        if name not in names:
            names.append(_tidy(name, 80))
        if len(names) >= 6:
            break
    return names


def _command_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value
    if isinstance(payload, dict):
        for key in ("cmd", "command", "script"):
            command = payload.get(key)
            if isinstance(command, str):
                return command
    return value


def _error_text(value: str) -> str:
    candidate = value
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("text"), str):
        candidate = payload["text"]
    elif isinstance(payload, list):
        texts = [
            str(item["text"])
            for item in payload
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        if texts:
            candidate = next(
                (text for text in reversed(texts) if not text.lower().startswith("script completed")),
                texts[-1],
            )
    stripped = SCRIPT_ENVELOPE.sub("", candidate.strip())
    return stripped or candidate


def _error_score(value: str) -> tuple[int, int]:
    lower = value.lower()
    signals = (
        "error",
        "failed",
        "failure",
        "exception",
        "traceback",
        "not found",
        "denied",
        "timeout",
        "timed out",
        "broken pipe",
    )
    return sum(signal in lower for signal in signals), -len(value)


def _normalize_exec_wrapper(value: str) -> tuple[str, str]:
    methods = re.findall(r"\btools\.([A-Za-z0-9_]+)\s*\(", value)
    unique_methods = list(dict.fromkeys(methods))
    if unique_methods == ["exec_command"]:
        command_match = re.search(r"\bcmd\s*:\s*(\"(?:\\.|[^\"])*\")", value, re.S)
        if command_match:
            try:
                return _normalize_shell(json.loads(command_match.group(1)))
            except json.JSONDecodeError:
                pass
        return "execute", "execute:shell"
    if unique_methods == ["apply_patch"]:
        return "edit", "edit:patch"
    if unique_methods == ["view_image"]:
        return "inspect", "inspect:image"
    if unique_methods == ["update_plan"]:
        return "plan", "plan:update"
    if unique_methods == ["web__run"]:
        return "research", "research:web"
    if len(unique_methods) == 1:
        nested_name = unique_methods[0]
        if nested_name in DIRECT_TOOL_ACTIONS:
            return DIRECT_TOOL_ACTIONS[nested_name]
        method = nested_name.replace("__", ":").replace("_", "-")
        return "other", f"tool:{method}"
    return "orchestrate", "orchestrate:batch"


def _normalize_shell(command: str) -> tuple[str, str]:
    first_line = next((line.strip() for line in command.splitlines() if line.strip()), "")
    first_line = SHELL_PREFIX.sub("", first_line)
    lower = first_line.lower()
    if re.search(r"\b(?:pytest|vitest|jest|bun test|npm test|cargo test|go test)\b", lower):
        runner = next(
            (name for name in ("pytest", "vitest", "jest", "bun", "npm", "cargo", "go") if name in lower),
            "test",
        )
        return "test", f"test:{runner}"
    if re.search(r"\b(?:ruff|mypy|pyright|tsc|eslint|prettier)\b", lower):
        tool = next(
            (name for name in ("ruff", "mypy", "pyright", "tsc", "eslint", "prettier") if name in lower),
            "check",
        )
        return "validate", f"validate:{tool}"
    match = re.search(r"(?:^|[;&|]\s*)(rg|grep|find|fd)\b", lower)
    if match:
        return "search", f"search:{match.group(1)}"
    match = re.search(r"(?:^|[;&|]\s*)(sed|head|tail|cat|ls|wc)\b", lower)
    if match:
        return "inspect", f"inspect:{match.group(1)}"
    match = re.search(r"\b(psql|sqlite3|mysql|duckdb)\b", lower)
    if match:
        return "database", f"database:{match.group(1)}"
    match = re.search(r"\bgit\s+([a-z-]+)", lower)
    if match:
        return "version-control", f"git:{match.group(1)}"
    match = re.search(r"\b(systemctl|docker|kubectl|tmux|tailscale)\b", lower)
    if match:
        return "operate", f"operate:{match.group(1)}"
    match = re.search(r"\b(curl|wget)\b", lower)
    if match:
        return "research", f"network:{match.group(1)}"
    match = re.search(r"\b(python3?|uv|node|bun|deno|cargo|go)\b", lower)
    if match:
        return "execute", f"execute:{match.group(1)}"
    executable = first_line.split(maxsplit=1)[0] if first_line else "shell"
    executable = PurePath(executable).name.lower() or "shell"
    return "execute", f"execute:{executable[:40]}"


def _empty_summary() -> dict[str, Any]:
    return {
        "occurrences": 0,
        "visible_occurrences": 0,
        "tool_calls": 0,
        "error_occurrences": 0,
        "corrections": 0,
        "discussion_occurrences": 0,
        "active_seconds": 0.0,
        "actions": [],
    }


def _method_note() -> str:
    return (
        "This first trace is deterministic: it uses bounded episode evidence, exact tool-call units, "
        "normalised operations, observed errors, and conservative correction phrases. Problem-family "
        "identity remains provisional until the evidence-signature extraction layer is added."
    )


def _tidy(value: str, limit: int) -> str:
    compact = SPACE_PATTERN.sub(" ", value).strip()
    return compact if len(compact) <= limit else f"{compact[: limit - 1]}…"


def _row(row: Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
