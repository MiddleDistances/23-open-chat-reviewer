from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from chatreview.db import Session
from chatreview.episodes import episode_stats
from chatreview.search import corpus_stats
from chatreview.semantic import semantic_run_freshness


def build_baseline_report(
    connection: Session,
    *,
    top: int = 30,
    min_sessions: int = 2,
) -> str:
    """Render evidence-backed repetition candidates without assigning causality."""
    top = min(max(top, 1), 200)
    min_sessions = max(min_sessions, 1)
    stats = corpus_stats(connection)
    lines = [
        "# Chat Corpus Baseline Review",
        "",
        f"Generated: `{datetime.now(UTC).isoformat().replace('+00:00', 'Z')}`  ",
        (
            "This is a triage surface: repeated text or commands are candidates for review, "
            "not proof of a shared cause or a blind spot."
        ),
        "",
        "## Corpus coverage",
        "",
        f"- Sources: **{stats['sources']:,}** ({_human_bytes(stats['source_bytes'])})",
        f"- Sessions: **{stats['sessions']:,}**",
        f"- Source events: **{stats['events']:,}**",
        f"- Searchable text units: **{stats['text_units']:,}**",
        f"- Extracted evidence artifacts: **{stats['artifacts']:,}**",
        f"- Parse-error records: **{stats['parse_errors']:,}**",
        "",
    ]
    lines.extend(_semantic_section(connection, top))
    lines.extend(_episode_section(connection, top))
    lines.extend(
        _repetition_section(
            connection,
            title="Repeated normalized error signatures",
            kind="error-signature",
            top=top,
            min_sessions=min_sessions,
        )
    )
    lines.extend(
        _repetition_section(
            connection,
            title="Repeated commands",
            kind="command",
            top=top,
            min_sessions=min_sessions,
        )
    )
    lines.extend(_long_session_section(connection, top))
    lines.extend(_project_section(connection, top))
    lines.extend(_review_section(connection))
    return "\n".join(lines).rstrip() + "\n"


def write_baseline_report(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _repetition_section(
    connection: Session,
    *,
    title: str,
    kind: str,
    top: int,
    min_sessions: int,
) -> list[str]:
    if kind == "error-signature":
        return _episode_error_repetition_section(
            connection,
            title=title,
            top=top,
            min_sessions=min_sessions,
        )
    evidence_filter = ""
    if kind == "command":
        evidence_filter = "AND length(trim(a.value)) >= 2"
    rows = connection.execute(
        f"""
        WITH grouped AS (
            SELECT a.value_hash,
                   MIN(a.value) AS value,
                   COUNT(*) AS physical_occurrences,
                   COUNT(DISTINCT CASE
                       WHEN e.event_type<>'compacted' AND sf.source_kind<>'history'
                       THEN COALESCE(e.canonical_event_id, e.id)
                   END) AS independent_occurrences,
                   COUNT(DISTINCT CASE
                       WHEN e.event_type<>'compacted' AND sf.source_kind<>'history'
                       THEN COALESCE(cs.id, -ce.id)
                   END) AS session_count,
                   COUNT(DISTINCT CASE
                       WHEN e.event_type<>'compacted' AND sf.source_kind<>'history'
                       THEN COALESCE(cs.project, '(unknown)')
                   END) AS project_count,
                   MIN(CASE
                       WHEN e.event_type<>'compacted' AND sf.source_kind<>'history'
                       THEN ce.id
                   END) AS representative_event_id
            FROM artifacts a
            JOIN events e ON e.id=a.event_id
            JOIN sources sf ON sf.id=e.source_id
            JOIN events ce ON ce.id=COALESCE(e.canonical_event_id, e.id)
            LEFT JOIN sessions cs ON cs.id=ce.session_id
            WHERE a.kind=?
              {evidence_filter}
            GROUP BY a.value_hash
        )
        SELECT *, physical_occurrences-independent_occurrences AS echoes_removed
        FROM grouped
        WHERE session_count>=? AND independent_occurrences>0
        ORDER BY session_count DESC, independent_occurrences DESC, value_hash
        LIMIT ?
        """,
        (kind, min_sessions, top),
    ).fetchall()
    lines = [f"## {title}", ""]
    if not rows:
        return [*lines, "No cross-session repetitions met the threshold.", ""]
    lines.extend(
        [
            "| Sessions | Projects | Independent | Echoes removed | "
            "Candidate evidence | Representative source |",
            "|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in rows:
        source = connection.execute(
            """
            SELECT sf.path, e.line_no FROM events e
            JOIN sources sf ON sf.id=e.source_id WHERE e.id=?
            """,
            (row["representative_event_id"],),
        ).fetchone()
        reference = f"`{_cell(source['path'], 180)}:{source['line_no']}`" if source else "(unavailable)"
        lines.append(
            f"| {row['session_count']:,} | {row['project_count']:,} | "
            f"{row['independent_occurrences']:,} | {row['echoes_removed']:,} | "
            f"`{_cell(row['value'], 420)}` | {reference} |"
        )
    return [*lines, ""]


def _episode_error_repetition_section(
    connection: Session,
    *,
    title: str,
    top: int,
    min_sessions: int,
) -> list[str]:
    rows = connection.execute(
        """
        WITH grouped AS (
            SELECT f.value_hash, MIN(f.value) AS value,
                   COUNT(DISTINCT ep.id) AS episode_count,
                   COUNT(DISTINCT ep.session_id) AS session_count,
                   COUNT(DISTINCT COALESCE(s.project, '(unknown)')) AS project_count,
                   MIN(ep.first_event_id) AS representative_event_id,
                   (
                       SELECT COUNT(*) FROM artifacts a
                       WHERE a.kind='error-signature' AND a.value_hash=f.value_hash
                   ) AS physical_hits
            FROM episode_fingerprints f
            JOIN episodes ep ON ep.id=f.episode_id
            JOIN sessions s ON s.id=ep.session_id
            WHERE f.kind='error-signature'
            GROUP BY f.value_hash
        )
        SELECT *, GREATEST(physical_hits-episode_count, 0) AS excluded_raw_hits
        FROM grouped
        WHERE session_count>=?
        ORDER BY session_count DESC, episode_count DESC, value_hash
        LIMIT ?
        """,
        (min_sessions, top),
    ).fetchall()
    lines = [f"## {title}", ""]
    if not rows:
        return [*lines, "No cross-session observed failures met the threshold.", ""]
    lines.extend(
        [
            "| Episodes | Sessions | Projects | Excluded raw hits | "
            "Observed failure evidence | Representative source |",
            "|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in rows:
        source = connection.execute(
            """
            SELECT sf.path, e.line_no FROM events e
            JOIN sources sf ON sf.id=e.source_id WHERE e.id=?
            """,
            (row["representative_event_id"],),
        ).fetchone()
        reference = (
            f"`{_cell(source['path'], 180)}:{source['line_no']}`"
            if source
            else "(unavailable)"
        )
        lines.append(
            f"| {row['episode_count']:,} | {row['session_count']:,} | "
            f"{row['project_count']:,} | {row['excluded_raw_hits']:,} | "
            f"`{_cell(row['value'], 420)}` | {reference} |"
        )
    return [*lines, ""]


def _episode_section(connection: Session, top: int) -> list[str]:
    stats = episode_stats(connection)
    lines = ["## Goal-attempt-result episodes", ""]
    if not stats["episodes"]:
        return [
            *lines,
            "No episode derivation is available. Run `chatreview episodes` first.",
            "",
        ]
    lines.extend(
        [
            f"- Episodes: **{stats['episodes']:,}** across **{stats['sessions']:,}** sessions",
            f"- Episodes with observed error evidence: **{stats['error_episodes']:,}**",
            f"- Tool attempts represented: **{stats['attempts']:,}**",
            f"- Gap-capped active time: **{stats['active_seconds'] / 3600:,.1f} hours**",
            f"- Shared-prefix provider events removed: **{stats['duplicate_events']:,}**",
            "",
            "Highest-volume episode projects:",
            "",
            "| Project | Episodes | Error episodes | Attempts | Active hours |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    rows = connection.execute(
        """
        SELECT COALESCE(s.project, '(unknown)') AS project,
               COUNT(*) AS episodes,
               SUM(CASE WHEN ep.error_count>0 THEN 1 ELSE 0 END) AS error_episodes,
               SUM(ep.attempt_count) AS attempts,
               SUM(ep.active_seconds)/3600.0 AS active_hours
        FROM episodes ep JOIN sessions s ON s.id=ep.session_id
        GROUP BY COALESCE(s.project, '(unknown)')
        ORDER BY error_episodes DESC, episodes DESC LIMIT ?
        """,
        (min(top, 50),),
    ).fetchall()
    lines.extend(
        f"| {_cell(row['project'], 180)} | {row['episodes']:,} | "
        f"{row['error_episodes']:,} | {row['attempts']:,} | {row['active_hours']:,.1f} |"
        for row in rows
    )
    return [*lines, ""]


def _semantic_section(connection: Session, top: int) -> list[str]:
    runs = connection.execute(
        """
        SELECT * FROM semantic_runs WHERE status='complete'
        ORDER BY CASE WHEN profile='conversation' THEN 0 ELSE 1 END,
                 completed_at DESC, id DESC LIMIT 20
        """
    ).fetchall()
    lines = ["## Semantic snapshot", ""]
    if not runs:
        return [*lines, "No completed semantic derivation is available.", ""]
    run = runs[0]
    run_data = {key: run[key] for key in run.keys()}
    config = _json(run["config_json"])
    freshness = semantic_run_freshness(connection, run_data)
    lines.extend(
        [
            f"- Run: `{run['run_key']}`",
            f"- Profile: **{config.get('profile', 'legacy')}**",
            f"- Windows: **{run['chunk_count']:,}**",
            f"- Indexed-snapshot freshness: **{freshness}**",
            "",
            "Selectable completed runs:",
            "",
            "| Profile | Run | Model | Dimensions | Windows | Freshness |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for available in runs:
        available_config = _json(available["config_json"])
        available_data = {key: available[key] for key in available.keys()}
        lines.append(
            f"| {available_config.get('profile', 'legacy')} | `{available['run_key']}` | "
            f"`{_cell(available['model_name'], 80)}` | {available['dimensions']} | "
            f"{available['chunk_count']:,} | "
            f"{semantic_run_freshness(connection, available_data)} |"
        )
    lines.extend(
        [
            "",
            "Largest clusters:",
            "",
            "| Cluster | Label | Windows |",
            "|---:|---|---:|",
        ]
    )
    clusters = connection.execute(
        """
        SELECT cluster_id, label, window_count FROM cluster_summaries
        WHERE run_id=? ORDER BY window_count DESC LIMIT ?
        """,
        (run["id"], min(top, 30)),
    ).fetchall()
    lines.extend(
        f"| {row['cluster_id']} | {_cell(row['label'] or '(unlabelled)', 160)} | {row['window_count']:,} |"
        for row in clusters
    )
    return [*lines, ""]


def _long_session_section(connection: Session, top: int) -> list[str]:
    rows = connection.execute(
        """
        SELECT id, provider, project, event_count, started_at, ended_at,
               CASE WHEN started_at IS NOT NULL AND ended_at IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (ended_at-started_at))/3600.0 END AS hours
        FROM sessions ORDER BY event_count DESC, hours DESC LIMIT ?
        """,
        (min(top, 50),),
    ).fetchall()
    lines = [
        "## Largest sessions",
        "",
        "Large sessions are review-priority candidates; size alone does not mean failure.",
        "",
        "| Session | Provider | Project | Events | Span hours |",
        "|---:|---|---|---:|---:|",
    ]
    for row in rows:
        hours = f"{row['hours']:.1f}" if row["hours"] is not None else "—"
        lines.append(
            f"| {row['id']} | {row['provider']} | {_cell(row['project'] or '(unknown)', 180)} | "
            f"{row['event_count']:,} | {hours} |"
        )
    return [*lines, ""]


def _project_section(connection: Session, top: int) -> list[str]:
    rows = connection.execute(
        """
        SELECT provider, COALESCE(project, '(unknown)') AS project,
               COUNT(*) AS sessions, SUM(event_count) AS events,
               SUM(text_unit_count) AS text_units
        FROM sessions GROUP BY provider, COALESCE(project, '(unknown)')
        ORDER BY events DESC LIMIT ?
        """,
        (min(top, 50),),
    ).fetchall()
    lines = [
        "## Highest-volume projects",
        "",
        "| Provider | Project | Sessions | Events | Text units |",
        "|---|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row['provider']} | {_cell(row['project'], 200)} | {row['sessions']:,} | "
        f"{row['events']:,} | {row['text_units']:,} |"
        for row in rows
    )
    return [*lines, ""]


def _review_section(connection: Session) -> list[str]:
    rows = connection.execute(
        """
        SELECT l.name, COUNT(a.id) AS count FROM labels l
        LEFT JOIN annotations a ON a.label_id=l.id GROUP BY l.id ORDER BY l.name
        """
    ).fetchall()
    lines = [
        "## Human review coverage",
        "",
        "| Label | Reviewed targets |",
        "|---|---:|",
    ]
    lines.extend(f"| {row['name']} | {row['count']:,} |" for row in rows)
    lines.extend(
        [
            "",
            'Continue in the terminal with `uv run chatreview review --query "…"`, or '
            "open the local browser with `uv run chatreview serve`.",
            "",
        ]
    )
    return lines


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _cell(value: str, limit: int) -> str:
    compact = " ".join(str(value).split())
    if len(compact) > limit:
        compact = compact[: limit - 1] + "…"
    return compact.replace("|", "\\|").replace("`", "'")


def _human_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"
