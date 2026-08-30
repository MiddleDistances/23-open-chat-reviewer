from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from chatreview.canonical import CanonicalSummary, reconcile_canonical_events
from chatreview.config import Settings
from chatreview.db import Session, database
from chatreview.providers.base import is_reportable_error_signature, stable_hash
from chatreview.search import build_fts_query
from chatreview.semantic import corpus_revision

SEGMENTATION_VERSION = 5
ACTIVE_GAP_CAP_SECONDS = 30 * 60
SESSION_BREAK_SECONDS = 12 * 60 * 60
SUCCESSFUL_TOOL_OUTPUT = re.compile(
    r"(?im)^(?:exit code:\s*0\b|process exited with code 0\b|script completed\b)"
)
COMMAND_NAME = re.compile(r"<command-name>\s*([^<]+?)\s*</command-name>", re.S)
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
PERSISTENT_OBJECTIVE = re.compile(r"<objective>\s*(.*?)\s*</objective>", re.S)

GOAL_KINDS = {"user-message"}
ATTEMPT_KINDS = {"tool-input", "reasoning"}
OUTCOME_KINDS = {"assistant-message", "agent-message", "message", "event-message"}
CONTEXT_KINDS = {"context-summary", "compaction-summary", "ai-title"}

CONTROL_MESSAGE_PREFIXES = (
    "# AGENTS.md instructions for ",
    "<codex_internal_context",
    "<environment_context>",
    "<goal_context>",
    "<local-command-caveat>",
    "<permissions instructions>",
    "<subagent_notification>",
    "<turn_aborted>",
)

ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class EpisodeBuildSummary:
    generation: str
    episodes: int
    sessions: int
    error_episodes: int
    attempts: int
    active_seconds: float
    canonical: CanonicalSummary
    reused: bool = False
    rebuilt_sessions: int = 0
    reused_sessions: int = 0


@dataclass(slots=True)
class UnitRecord:
    kind: str
    label: str | None
    text: str
    is_error: bool


@dataclass(slots=True)
class ArtifactRecord:
    kind: str
    value: str
    value_hash: str


@dataclass(slots=True)
class EventRecord:
    id: int
    event_key: str
    event_fingerprint: str | None
    timestamp: datetime | str | None
    event_type: str
    subtype: str | None
    role: str | None
    turn_id: str | None
    provider_event_id: str | None = None
    units: list[UnitRecord] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)


@dataclass(slots=True)
class EpisodeDraft:
    events: list[EventRecord] = field(default_factory=list)
    turn_id: str | None = None
    has_goal: bool = False
    has_progress_after_goal: bool = False

    def append(self, event: EventRecord) -> None:
        has_goal = _event_has_goal(event)
        has_progress = _event_has_activity(event) or _event_has_outcome(event)
        self.events.append(event)
        if self.turn_id is None and event.turn_id:
            self.turn_id = event.turn_id
        if self.has_goal and has_progress:
            self.has_progress_after_goal = True
        self.has_goal = self.has_goal or has_goal


class EpisodeBuilder:
    def __init__(
        self,
        settings: Settings,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self.progress = progress or (lambda _message: None)

    def run(self, *, force: bool = False) -> EpisodeBuildSummary:
        self.settings.ensure_output_dirs()
        with database(self.settings.database_url) as connection:
            revision = corpus_revision(connection)
            current_generation = connection.execute(
                "SELECT value FROM schema_meta WHERE key='episode_generation'"
            ).fetchone()
            current_version = connection.execute(
                "SELECT value FROM schema_meta WHERE key='episode_segmentation_version'"
            ).fetchone()
            episode_revision = connection.execute(
                "SELECT value FROM schema_meta WHERE key='episode_corpus_revision'"
            ).fetchone()
            version_current = bool(
                current_version and current_version["value"] == str(SEGMENTATION_VERSION)
            )
            generation = (
                str(current_generation["value"])
                if current_generation and version_current
                else stable_hash(f"episodes\0{SEGMENTATION_VERSION}")[:24]
            )
            if (
                current_generation
                and version_current
                and episode_revision
                and episode_revision["value"] == revision
                and not force
            ):
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM episodes WHERE generation=?", (generation,)
                    ).fetchone()[0]
                )
                if count:
                    reused_sessions = int(
                        connection.execute(
                            """
                            SELECT COUNT(*) FROM episode_session_state
                            WHERE segmentation_version=?
                            """,
                            (SEGMENTATION_VERSION,),
                        ).fetchone()[0]
                    )
                    return self._summary(
                        connection,
                        generation,
                        CanonicalSummary(0, 0, _duplicate_event_count(connection)),
                        reused=True,
                        reused_sessions=reused_sessions,
                    )

            self.progress("Canonicalizing shared provider events")
            canonical = reconcile_canonical_events(connection, progress=self.progress)
            self._prepare_session_inputs(connection)
            rebuild_all = force or not version_current
            sessions = self._changed_sessions(connection, rebuild_all=rebuild_all)
            stale_session_ids = [
                int(row["session_id"])
                for row in connection.execute(
                    """
                    SELECT state.session_id
                    FROM episode_session_state state
                    LEFT JOIN episode_session_inputs input ON input.session_id=state.session_id
                    WHERE input.session_id IS NULL
                    ORDER BY state.session_id
                    """
                ).fetchall()
            ]
            input_count = int(
                connection.execute("SELECT COUNT(*) FROM episode_session_inputs").fetchone()[0]
            )
            reused_sessions = max(0, input_count - len(sessions))
            self.progress(
                f"Segmenting {len(sessions):,} changed sessions; "
                f"reusing {reused_sessions:,} unchanged sessions"
            )

            if stale_session_ids:
                connection.execute(
                    "DELETE FROM episodes WHERE session_id=ANY(?)", (stale_session_ids,)
                )
                connection.execute(
                    "DELETE FROM episode_session_state WHERE session_id=ANY(?)",
                    (stale_session_ids,),
                )

            episode_count = 0
            for session_index, session in enumerate(sessions, start=1):
                session_id = int(session["id"])
                connection.execute("DELETE FROM episodes WHERE session_id=?", (session_id,))
                tracks = _load_session_event_tracks(connection, int(session["id"]))
                sequence_no = 0
                for events in tracks:
                    for draft in _segment_events(events):
                        self._persist_episode(
                            connection,
                            generation=generation,
                            session_id=int(session["id"]),
                            session_key=session["session_key"],
                            sequence_no=sequence_no,
                            draft=draft,
                        )
                        sequence_no += 1
                        episode_count += 1
                self._record_session_state(
                    connection,
                    session_id=session_id,
                    input_event_count=int(session["input_event_count"]),
                    input_max_event_id=int(session["input_max_event_id"]),
                    input_event_id_sum=session["input_event_id_sum"],
                    episode_count=sequence_no,
                )
                if session_index % 25 == 0:
                    connection.commit()
                    self.progress(
                        f"  rebuilt {session_index:,}/{len(sessions):,} changed sessions "
                        f"({episode_count:,} episodes)"
                    )

            connection.execute("DELETE FROM episodes WHERE generation<>?", (generation,))
            connection.execute(
                """
                INSERT INTO schema_meta(key, value) VALUES ('episode_generation', ?)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
                """,
                (generation,),
            )
            connection.execute(
                """
                INSERT INTO schema_meta(key, value) VALUES ('episode_corpus_revision', ?)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
                """,
                (revision,),
            )
            connection.execute(
                """
                INSERT INTO schema_meta(key, value)
                VALUES ('episode_segmentation_version', ?)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value
                """,
                (str(SEGMENTATION_VERSION),),
            )
            connection.commit()
            return self._summary(
                connection,
                generation,
                canonical,
                reused=not sessions and not stale_session_ids,
                rebuilt_sessions=len(sessions),
                reused_sessions=reused_sessions,
            )

    @staticmethod
    def _prepare_session_inputs(connection: Session) -> None:
        """Materialize compact revisions for the effective events in each session."""

        connection.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS episode_session_inputs (
                session_id bigint PRIMARY KEY,
                input_event_count bigint NOT NULL,
                input_max_event_id bigint NOT NULL,
                input_event_id_sum numeric NOT NULL
            ) ON COMMIT PRESERVE ROWS
            """
        )
        connection.execute("TRUNCATE episode_session_inputs")
        connection.execute(
            """
            INSERT INTO episode_session_inputs(
                session_id, input_event_count, input_max_event_id, input_event_id_sum
            )
            SELECT event.session_id, COUNT(*), MAX(event.id), SUM(event.id::numeric)
            FROM events event
            JOIN sources source ON source.id=event.source_id
            WHERE event.session_id IS NOT NULL
              AND event.canonical_event_id IS NULL
              AND source.source_kind<>'history'
              AND event.event_type NOT IN (
                  'compacted', 'parse-error', 'last-prompt', 'ai-title'
              )
              AND EXISTS (SELECT 1 FROM text_units unit WHERE unit.event_id=event.id)
            GROUP BY event.session_id
            """
        )
        connection.execute("ANALYZE episode_session_inputs")

    @staticmethod
    def _changed_sessions(connection: Session, *, rebuild_all: bool) -> list[Any]:
        return connection.execute(
            """
            SELECT session.id, session.session_key, input.input_event_count,
                   input.input_max_event_id, input.input_event_id_sum
            FROM episode_session_inputs input
            JOIN sessions session ON session.id=input.session_id
            LEFT JOIN episode_session_state state ON state.session_id=input.session_id
            WHERE ?
               OR state.session_id IS NULL
               OR state.segmentation_version<>?
               OR state.input_event_count<>input.input_event_count
               OR state.input_max_event_id<>input.input_max_event_id
               OR state.input_event_id_sum<>input.input_event_id_sum
            ORDER BY session.id
            """,
            (rebuild_all, SEGMENTATION_VERSION),
        ).fetchall()

    @staticmethod
    def _record_session_state(
        connection: Session,
        *,
        session_id: int,
        input_event_count: int,
        input_max_event_id: int,
        input_event_id_sum: Any,
        episode_count: int,
    ) -> None:
        connection.execute(
            """
            INSERT INTO episode_session_state(
                session_id, segmentation_version, input_event_count,
                input_max_event_id, input_event_id_sum, episode_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                segmentation_version=EXCLUDED.segmentation_version,
                input_event_count=EXCLUDED.input_event_count,
                input_max_event_id=EXCLUDED.input_max_event_id,
                input_event_id_sum=EXCLUDED.input_event_id_sum,
                episode_count=EXCLUDED.episode_count,
                built_at=clock_timestamp(),
                updated_at=clock_timestamp()
            """,
            (
                session_id,
                SEGMENTATION_VERSION,
                input_event_count,
                input_max_event_id,
                input_event_id_sum,
                episode_count,
            ),
        )

    def _persist_episode(
        self,
        connection: Session,
        *,
        generation: str,
        session_id: int,
        session_key: str,
        sequence_no: int,
        draft: EpisodeDraft,
    ) -> None:
        rendered = _render_episode(draft.events)
        first = draft.events[0]
        last = draft.events[-1]
        # This logical key deliberately excludes PostgreSQL IDs, source revisions and
        # machine paths. Sequence position distinguishes repeated identical attempts;
        # provider identity and the semantic fingerprint keep rebuilds stable.
        anchor = first.provider_event_id or first.event_fingerprint or "unidentified"
        episode_key = stable_hash(
            f"{session_key}\0{sequence_no}\0{anchor}\0{first.event_fingerprint or ''}"
        )
        goal_id = _upsert_content(connection, rendered["goal"]) if rendered["goal"] else None
        outcome_id = _upsert_content(connection, rendered["outcome"]) if rendered["outcome"] else None
        document_id = _upsert_content(connection, rendered["document"])
        active_seconds = _active_seconds(draft.events)
        connection.execute(
            """
            INSERT INTO episodes(
                episode_key, generation, segmentation_version, session_id, sequence_no,
                first_event_id, last_event_id, started_at, ended_at, active_seconds,
                goal_content_id, outcome_content_id, document_content_id, event_count,
                attempt_count, error_count, evidence_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(episode_key) DO UPDATE SET
                generation=excluded.generation,
                segmentation_version=excluded.segmentation_version,
                session_id=excluded.session_id,
                sequence_no=excluded.sequence_no,
                first_event_id=excluded.first_event_id,
                last_event_id=excluded.last_event_id,
                started_at=excluded.started_at,
                ended_at=excluded.ended_at,
                active_seconds=excluded.active_seconds,
                goal_content_id=excluded.goal_content_id,
                outcome_content_id=excluded.outcome_content_id,
                document_content_id=excluded.document_content_id,
                event_count=excluded.event_count,
                attempt_count=excluded.attempt_count,
                error_count=excluded.error_count,
                evidence_state=excluded.evidence_state,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                episode_key,
                generation,
                SEGMENTATION_VERSION,
                session_id,
                sequence_no,
                first.id,
                last.id,
                first.timestamp,
                last.timestamp,
                active_seconds,
                goal_id,
                outcome_id,
                document_id,
                len(draft.events),
                rendered["attempt_count"],
                rendered["error_count"],
                rendered["evidence_state"],
            ),
        )
        episode_id = int(
            connection.execute("SELECT id FROM episodes WHERE episode_key=?", (episode_key,)).fetchone()[0]
        )
        connection.execute("DELETE FROM episode_events WHERE episode_id=?", (episode_id,))
        connection.execute("DELETE FROM episode_fingerprints WHERE episode_id=?", (episode_id,))
        connection.executemany(
            """
            INSERT INTO episode_events(episode_id, event_id, position, section)
            VALUES (?, ?, ?, ?)
            """,
            [
                (episode_id, event.id, position, _event_section(event))
                for position, event in enumerate(draft.events)
            ],
        )
        fingerprints = _episode_fingerprints(draft.events)
        connection.executemany(
            """
            INSERT INTO episode_fingerprints(episode_id, kind, value, value_hash)
            VALUES (?, ?, ?, ?)
            """,
            [(episode_id, artifact.kind, artifact.value, artifact.value_hash) for artifact in fingerprints],
        )

    @staticmethod
    def _summary(
        connection: Session,
        generation: str,
        canonical: CanonicalSummary,
        *,
        reused: bool = False,
        rebuilt_sessions: int = 0,
        reused_sessions: int = 0,
    ) -> EpisodeBuildSummary:
        row = connection.execute(
            """
            SELECT COUNT(*) AS episodes,
                   COUNT(DISTINCT session_id) AS sessions,
                   SUM(CASE WHEN error_count>0 THEN 1 ELSE 0 END) AS error_episodes,
                   COALESCE(SUM(attempt_count), 0) AS attempts,
                   COALESCE(SUM(active_seconds), 0) AS active_seconds
            FROM episodes WHERE generation=?
            """,
            (generation,),
        ).fetchone()
        return EpisodeBuildSummary(
            generation=generation,
            episodes=int(row["episodes"]),
            sessions=int(row["sessions"]),
            error_episodes=int(row["error_episodes"] or 0),
            attempts=int(row["attempts"]),
            active_seconds=float(row["active_seconds"]),
            canonical=canonical,
            reused=reused,
            rebuilt_sessions=rebuilt_sessions,
            reused_sessions=reused_sessions,
        )


def episode_stats(connection: Session) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT COUNT(*) AS episodes,
               COUNT(DISTINCT session_id) AS sessions,
               SUM(CASE WHEN error_count>0 THEN 1 ELSE 0 END) AS error_episodes,
               COALESCE(SUM(attempt_count), 0) AS attempts,
               COALESCE(SUM(active_seconds), 0) AS active_seconds
        FROM episodes
        """
    ).fetchone()
    generation = connection.execute("SELECT value FROM schema_meta WHERE key='episode_generation'").fetchone()
    return {
        **{key: row[key] for key in row.keys()},
        "generation": generation["value"] if generation else None,
        "duplicate_events": _duplicate_event_count(connection),
    }


def list_episodes(
    connection: Session,
    *,
    query: str | None = None,
    provider: str | None = None,
    project: str | None = None,
    evidence_state: str | None = None,
    errors_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    parameters: list[Any] = []
    joins = "JOIN contents d ON d.id=ep.document_content_id"
    score = "NULL AS lexical_score"
    if query:
        joins += " CROSS JOIN LATERAL (SELECT plainto_tsquery('simple', ?) AS q) lex"
        clauses.append("d.search_vector @@ lex.q")
        parameters.append(build_fts_query(query))
        score = "ts_rank_cd(d.search_vector, lex.q)::double precision AS lexical_score"
    if provider:
        clauses.append("s.provider=?")
        parameters.append(provider)
    if project:
        clauses.append("s.project=?")
        parameters.append(project)
    if evidence_state:
        clauses.append("ep.evidence_state=?")
        parameters.append(evidence_state)
    if errors_only:
        clauses.append("ep.error_count>0")
    parameters.extend([min(max(limit, 1), 500), max(offset, 0)])
    rows = connection.execute(
        f"""
        SELECT ep.id, ep.episode_key, ep.sequence_no, ep.started_at, ep.ended_at,
               ep.active_seconds, ep.event_count, ep.attempt_count, ep.error_count,
               ep.evidence_state, ep.first_event_id, ep.last_event_id,
               s.id AS session_id, s.provider, s.project,
               substr(g.text, 1, 1000) AS goal,
               substr(o.text, 1, 1000) AS outcome,
               substr(d.text, 1, 3000) AS document,
               {score}
        FROM episodes ep
        JOIN sessions s ON s.id=ep.session_id
        {joins}
        LEFT JOIN contents g ON g.id=ep.goal_content_id
        LEFT JOIN contents o ON o.id=ep.outcome_content_id
        WHERE {" AND ".join(clauses)}
        ORDER BY {"lexical_score DESC," if query else ""}
                 COALESCE(ep.ended_at, ep.started_at) DESC NULLS LAST, ep.id DESC
        LIMIT ? OFFSET ?
        """,
        parameters,
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def get_episode(connection: Session, episode_id: int) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT ep.*, s.session_key, s.external_id, s.provider, s.project,
               g.text AS goal, o.text AS outcome, d.text AS document
        FROM episodes ep
        JOIN sessions s ON s.id=ep.session_id
        LEFT JOIN contents g ON g.id=ep.goal_content_id
        LEFT JOIN contents o ON o.id=ep.outcome_content_id
        JOIN contents d ON d.id=ep.document_content_id
        WHERE ep.id=?
        """,
        (episode_id,),
    ).fetchone()
    if row is None:
        return None
    result = {key: row[key] for key in row.keys()}
    result["events"] = [
        {key: event[key] for key in event.keys()}
        for event in connection.execute(
            """
            SELECT ee.position, ee.section, e.id, e.event_key, e.timestamp,
                   e.event_type, e.subtype, e.role
            FROM episode_events ee JOIN events e ON e.id=ee.event_id
            WHERE ee.episode_id=? ORDER BY ee.position
            """,
            (episode_id,),
        ).fetchall()
    ]
    result["fingerprints"] = [
        {key: item[key] for key in item.keys()}
        for item in connection.execute(
            """
            SELECT kind, value, value_hash FROM episode_fingerprints
            WHERE episode_id=? ORDER BY kind, value
            """,
            (episode_id,),
        ).fetchall()
    ]
    return result


def _load_session_event_tracks(connection: Session, session_id: int) -> list[list[EventRecord]]:
    rows = connection.execute(
        """
        SELECT e.id, e.source_id, e.event_key, e.event_fingerprint, e.provider_event_id,
               e.timestamp, e.event_type,
               e.subtype, e.role, e.turn_id, t.unit_index, t.kind, t.label,
               t.is_error, c.text
        FROM events e
        JOIN sources sf ON sf.id=e.source_id
        JOIN text_units t ON t.event_id=e.id
        JOIN contents c ON c.id=t.content_id
        WHERE e.session_id=?
          AND e.canonical_event_id IS NULL
          AND sf.source_kind<>'history'
          AND e.event_type NOT IN ('compacted', 'parse-error', 'last-prompt', 'ai-title')
        ORDER BY CASE sf.source_kind WHEN 'session' THEN 0 ELSE 1 END,
                 sf.path, e.timestamp NULLS FIRST, e.ordinal, e.id, t.unit_index
        """,
        (session_id,),
    ).fetchall()
    tracks: dict[int, list[EventRecord]] = {}
    by_id: dict[int, EventRecord] = {}
    for row in rows:
        event_id = int(row["id"])
        event = by_id.get(event_id)
        if event is None:
            event = EventRecord(
                id=event_id,
                event_key=row["event_key"],
                event_fingerprint=row["event_fingerprint"],
                provider_event_id=row["provider_event_id"],
                timestamp=row["timestamp"],
                event_type=row["event_type"],
                subtype=row["subtype"],
                role=row["role"],
                turn_id=row["turn_id"],
            )
            by_id[event_id] = event
            tracks.setdefault(int(row["source_id"]), []).append(event)
        event.units.append(
            UnitRecord(
                kind=row["kind"],
                label=row["label"],
                text=row["text"],
                is_error=bool(row["is_error"]),
            )
        )
    if not tracks:
        return []
    artifact_rows = connection.execute(
        """
        SELECT a.event_id, a.kind, a.value, a.value_hash
        FROM artifacts a JOIN events e ON e.id=a.event_id
        JOIN sources sf ON sf.id=e.source_id
        WHERE e.session_id=?
          AND e.canonical_event_id IS NULL
          AND sf.source_kind<>'history'
          AND e.event_type NOT IN ('compacted', 'parse-error', 'last-prompt', 'ai-title')
          AND a.kind IN ('error-signature', 'command', 'tool', 'path', 'code-block')
        ORDER BY a.event_id, a.id
        """,
        (session_id,),
    ).fetchall()
    for row in artifact_rows:
        event = by_id.get(int(row["event_id"]))
        if event is not None:
            event.artifacts.append(ArtifactRecord(row["kind"], row["value"], row["value_hash"]))
    return list(tracks.values())


def _segment_events(events: Iterable[EventRecord]) -> list[EpisodeDraft]:
    episodes: list[EpisodeDraft] = []
    current: EpisodeDraft | None = None
    for event in events:
        if not event.units:
            continue
        if current is not None and _starts_new_episode(current, event):
            if current.events:
                episodes.append(current)
            current = None
        if current is None:
            current = EpisodeDraft()
        current.append(event)
    if current is not None and current.events:
        episodes.append(current)
    return episodes


def _starts_new_episode(current: EpisodeDraft, event: EventRecord) -> bool:
    if not current.events:
        return False
    has_goal = _event_has_goal(event)
    gap = _timestamp_gap(current.events[-1].timestamp, event.timestamp)
    if has_goal and current.has_goal and current.has_progress_after_goal:
        return True
    if has_goal and gap is not None and gap >= SESSION_BREAK_SECONDS:
        return True
    return bool(gap is not None and gap >= SESSION_BREAK_SECONDS and _event_has_activity(event))


def _event_has_goal(event: EventRecord) -> bool:
    return any(_unit_is_goal(unit) for unit in event.units)


def _event_has_activity(event: EventRecord) -> bool:
    return any(unit.kind in ATTEMPT_KINDS or unit.kind == "tool-output" for unit in event.units)


def _event_has_outcome(event: EventRecord) -> bool:
    return any(unit.kind in OUTCOME_KINDS for unit in event.units)


def _unit_is_goal(unit: UnitRecord) -> bool:
    return _goal_text(unit) is not None


def _goal_text(unit: UnitRecord) -> str | None:
    if unit.kind not in GOAL_KINDS:
        return None
    text = unit.text.strip()
    command = COMMAND_NAME.search(text)
    if command:
        arguments = COMMAND_ARGS.search(text)
        if command.group(1).strip() == "/goal" and arguments and arguments.group(1).strip():
            return arguments.group(1).strip()
        return None
    return None if _is_control_message(text) else text


def _persistent_objective(value: str) -> str | None:
    text = value.lstrip()
    if not text.startswith(("<codex_internal_context", "<goal_context>")):
        return None
    match = PERSISTENT_OBJECTIVE.search(text)
    return match.group(1).strip() if match and match.group(1).strip() else None


def _is_control_message(value: str) -> bool:
    text = value.lstrip()
    return any(text.startswith(prefix) for prefix in CONTROL_MESSAGE_PREFIXES)


def _event_section(event: EventRecord) -> str:
    sections = set()
    for unit in event.units:
        if _unit_is_goal(unit):
            sections.add("goal")
        elif _persistent_objective(unit.text):
            sections.add("objective")
        elif unit.kind in GOAL_KINDS and _is_control_message(unit.text):
            sections.add("metadata")
        elif unit.is_error or unit.kind == "error":
            sections.add("error")
        elif unit.kind in ATTEMPT_KINDS:
            sections.add("attempt")
        elif unit.kind == "tool-output":
            sections.add("result")
        elif unit.kind in OUTCOME_KINDS:
            sections.add("outcome")
        elif unit.kind in CONTEXT_KINDS:
            sections.add("context")
    return next(iter(sections)) if len(sections) == 1 else "mixed"


def _render_episode(events: list[EventRecord]) -> dict[str, Any]:
    sections: dict[str, list[str]] = defaultdict(list)
    attempt_events: set[int] = set()
    error_values: set[str] = set()
    for event in events:
        actionable_errors = set()
        if _event_has_observed_failure(event):
            actionable_errors = {
                item.value
                for item in event.artifacts
                if item.kind == "error-signature" and is_reportable_error_signature(item.value)
            }
        error_values.update(stable_hash(value) for value in actionable_errors)
        for unit in event.units:
            text = _bounded(unit.text, 4_000)
            label = f"[{unit.label}] " if unit.label else ""
            goal_text = _goal_text(unit)
            objective = _persistent_objective(unit.text)
            if goal_text:
                sections["GOAL"].append(_bounded(goal_text, 4_000))
            elif objective:
                sections["OBJECTIVE"].append(_bounded(objective, 4_000))
            elif unit.kind in GOAL_KINDS and _is_control_message(unit.text):
                continue
            elif unit.is_error or unit.kind == "error":
                sections["ERROR EVIDENCE"].append(f"{label}{text}")
                error_values.add(stable_hash(text))
            elif unit.kind == "tool-input":
                attempt_events.add(event.id)
                sections["ATTEMPTS"].append(f"{label}{text}")
            elif unit.kind == "reasoning":
                sections["REASONING"].append(text)
            elif unit.kind == "tool-output":
                destination = "ERROR EVIDENCE" if actionable_errors else "RESULTS"
                sections[destination].append(f"{label}{text}")
            elif unit.kind in OUTCOME_KINDS:
                sections["OUTCOME MESSAGES"].append(text)
            elif unit.kind in CONTEXT_KINDS:
                sections["CONTEXT"].append(text)
    explicit_goal = "\n\n".join(_dedupe_text(sections["GOAL"]))[-12_000:]
    objectives = _dedupe_text(sections["OBJECTIVE"])
    goal = explicit_goal or (objectives[-1] if objectives else "")
    outcome = "\n\n".join(sections["OUTCOME MESSAGES"])[-12_000:]
    ordered = [
        "OBJECTIVE",
        "GOAL",
        "CONTEXT",
        "REASONING",
        "ATTEMPTS",
        "RESULTS",
        "ERROR EVIDENCE",
        "OUTCOME MESSAGES",
    ]
    document_parts = []
    for name in ordered:
        values = _dedupe_text(sections[name])
        if values:
            document_parts.append(f"[{name}]\n" + "\n\n".join(values))
    attempt_count = len(attempt_events)
    error_count = len(error_values)
    if error_count:
        evidence_state = "error-observed"
    elif attempt_count and outcome:
        evidence_state = "result-observed"
    elif attempt_count:
        evidence_state = "attempt-observed"
    else:
        evidence_state = "discussion"
    return {
        "goal": goal,
        "outcome": outcome,
        "document": _bounded("\n\n".join(document_parts), 24_000),
        "attempt_count": attempt_count,
        "error_count": error_count,
        "evidence_state": evidence_state,
    }


def _episode_fingerprints(events: Iterable[EventRecord]) -> list[ArtifactRecord]:
    fingerprints: dict[tuple[str, str], ArtifactRecord] = {}
    per_kind: defaultdict[str, int] = defaultdict(int)
    for event in events:
        observed_failure = _event_has_observed_failure(event)
        for item in event.artifacts:
            if item.kind == "error-signature" and (
                not observed_failure or not is_reportable_error_signature(item.value)
            ):
                continue
            if item.kind not in {"error-signature", "command", "tool", "path", "code-block"}:
                continue
            if per_kind[item.kind] >= 100:
                continue
            key = (item.kind, item.value_hash)
            if key not in fingerprints:
                fingerprints[key] = item
                per_kind[item.kind] += 1
    return list(fingerprints.values())


def _event_has_observed_failure(event: EventRecord) -> bool:
    if any(unit.is_error or unit.kind == "error" for unit in event.units):
        return True
    tool_outputs = [unit.text for unit in event.units if unit.kind == "tool-output"]
    return bool(
        tool_outputs
        and not any(SUCCESSFUL_TOOL_OUTPUT.search(output) for output in tool_outputs)
        and any(
            item.kind == "error-signature" and is_reportable_error_signature(item.value)
            for item in event.artifacts
        )
    )


def _active_seconds(events: list[EventRecord]) -> float:
    timestamps = [_parse_timestamp(event.timestamp) for event in events]
    valid = [timestamp for timestamp in timestamps if timestamp is not None]
    total = 0.0
    for previous, current in zip(valid, valid[1:], strict=False):
        gap = (current - previous).total_seconds()
        if gap >= 0:
            total += min(gap, ACTIVE_GAP_CAP_SECONDS)
    return total


def _timestamp_gap(
    left: datetime | str | None, right: datetime | str | None
) -> float | None:
    start = _parse_timestamp(left)
    end = _parse_timestamp(right)
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _parse_timestamp(value: datetime | str | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _upsert_content(connection: Session, text: str) -> int:
    content_hash = stable_hash(text)
    row = connection.execute("SELECT id FROM contents WHERE content_hash=?", (content_hash,)).fetchone()
    if row:
        return int(row["id"])
    inserted = connection.execute(
        """
        INSERT INTO contents(content_hash, text, char_count) VALUES (?, ?, ?)
        RETURNING id
        """,
        (content_hash, text, len(text)),
    ).fetchone()
    assert inserted is not None
    return int(inserted["id"])


def _duplicate_event_count(connection: Session) -> int:
    return int(
        connection.execute("SELECT COUNT(*) FROM events WHERE canonical_event_id IS NOT NULL").fetchone()[0]
    )


def _bounded(value: str, limit: int) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dedupe_text(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        identity = stable_hash(value)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(value)
    return result


def write_episode_summary(path: Path, summary: EpisodeBuildSummary) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    active_hours = summary.active_seconds / 3600
    content = (
        "# Episode Derivation\n\n"
        f"- Generation: `{summary.generation}`\n"
        f"- Episodes: **{summary.episodes:,}**\n"
        f"- Sessions represented: **{summary.sessions:,}**\n"
        f"- Episodes with observed errors: **{summary.error_episodes:,}**\n"
        f"- Tool attempts: **{summary.attempts:,}**\n"
        f"- Gap-capped active time: **{active_hours:,.1f} hours**\n"
        f"- Shared-prefix events removed: **{summary.canonical.duplicate_events:,}**\n"
    )
    path.write_text(content, encoding="utf-8")
    return path
