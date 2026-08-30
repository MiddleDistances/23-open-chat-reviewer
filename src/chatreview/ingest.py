from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import orjson
import psycopg

from chatreview.canonical import parsed_event_fingerprint
from chatreview.config import Settings
from chatreview.db import DatabaseError, Row, Session, close_pools, database
from chatreview.providers.base import ProviderAdapter, stable_hash
from chatreview.registry import apply_contributor_rules, rebuild_registry
from chatreview.retention import RawRetentionPolicy
from chatreview.source_selection import HistoryScope, SourceSelectionPreview, preview_source_selection
from chatreview.types import ParsedRecord, SourceSpec, TextFragment

ProgressCallback = Callable[[str], None]
MAX_SEARCHABLE_FRAGMENT_CHARS = 100_000


@dataclass(slots=True)
class IngestSummary:
    discovered_files: int = 0
    processed_files: int = 0
    skipped_files: int = 0
    reparsed_files: int = 0
    events: int = 0
    text_units: int = 0
    artifacts: int = 0
    parse_errors: int = 0
    bytes_read: int = 0
    excluded_files: int = 0
    exact_files: int = 0
    mtime_bound_files: int = 0
    aggregate_files: int = 0
    unbounded_files: int = 0


@dataclass(frozen=True, slots=True)
class RawLine:
    line_no: int
    byte_offset: int
    payload: bytes
    payload_hash: str


@dataclass(slots=True)
class SessionCacheEntry:
    id: int
    project: str | None
    cwd: str | None
    parent_session_id: str | None
    has_metadata: bool


@dataclass(frozen=True, slots=True)
class _ProjectionBatchResult:
    events: int
    text_units: int
    artifacts: int
    parse_errors: int


class _ProjectionBatchWriter:
    """Persist one parsed source batch with set-based PostgreSQL identity resolution."""

    def __init__(self, settings: Settings, contributor_id: int | None) -> None:
        self.settings = settings
        self.contributor_id = contributor_id

    def persist(
        self,
        connection: Session,
        *,
        source_id: int,
        revision_id: int,
        source: SourceSpec,
        raw_ids: dict[int, int],
        parsed_items: list[tuple[RawLine, list[ParsedRecord] | None, str | None]],
    ) -> _ProjectionBatchResult:
        sessions: dict[str, list[Any]] = {}
        contents: dict[str, tuple[str, int]] = {}
        events: list[tuple[Any, ...]] = []
        text_units: list[tuple[Any, ...]] = []
        artifacts: list[tuple[Any, ...]] = []
        parse_errors = 0

        for item, parsed_records, error in parsed_items:
            if parsed_records is None:
                event_key = _event_key(
                    source.provider,
                    revision_id,
                    item.line_no,
                    item.payload_hash,
                )
                parse_errors += 1
                events.append(
                    (
                        event_key,
                        source_id,
                        revision_id,
                        raw_ids[item.line_no],
                        0,
                        None,
                        item.line_no,
                        item.line_no,
                        item.byte_offset,
                        len(item.payload),
                        None,
                        "parse-error",
                        "invalid-record",
                        None,
                        None,
                        None,
                        None,
                        item.payload_hash,
                        None,
                        "{}",
                        (error or "unknown parse error")[:8192],
                    )
                )
                continue
            record_count = len(parsed_records)
            for record_index, parsed in enumerate(parsed_records):
                event_key = _event_key(
                    source.provider,
                    revision_id,
                    item.line_no,
                    item.payload_hash,
                    record_index=record_index,
                    record_count=record_count,
                )
                event_ordinal = item.line_no if record_count == 1 else record_index + 1
                timestamp = normalize_timestamp(parsed.timestamp)
                metadata_json = _postgres_json(parsed.metadata)
                session_key = None
                if parsed.session_external_id:
                    session_key = stable_hash(f"{parsed.provider}\0{parsed.session_external_id}")
                    session_row = [
                        session_key,
                        parsed.provider,
                        _postgres_text(parsed.session_external_id),
                        _postgres_text(parsed.project),
                        _postgres_text(parsed.cwd),
                        timestamp,
                        _postgres_text(parsed.parent_session_external_id),
                        metadata_json,
                        self.settings.machine_id,
                        self.contributor_id,
                    ]
                    existing = sessions.get(session_key)
                    if existing is None:
                        sessions[session_key] = session_row
                    else:
                        for index in (3, 4, 5, 6):
                            if existing[index] is None and session_row[index] is not None:
                                existing[index] = session_row[index]
                        if existing[7] == "{}" and metadata_json != "{}":
                            existing[7] = metadata_json

                event_fingerprint = parsed_event_fingerprint(source.provider, parsed)
                provider_event_id = parsed.provider_event_id or stable_hash(
                    orjson.dumps(
                        [
                            "derived-provider-event-v1",
                            source.provider,
                            parsed.session_external_id,
                            timestamp.isoformat() if timestamp else None,
                            parsed.parent_event_id,
                            parsed.turn_id,
                            event_fingerprint,
                        ]
                    )
                )
                events.append(
                    (
                        event_key,
                        source_id,
                        revision_id,
                        raw_ids[item.line_no],
                        record_index,
                        session_key,
                        event_ordinal,
                        item.line_no,
                        item.byte_offset,
                        len(item.payload),
                        timestamp,
                        parsed.event_type,
                        parsed.subtype,
                        parsed.role,
                        _postgres_text(provider_event_id),
                        _postgres_text(parsed.parent_event_id),
                        _postgres_text(parsed.turn_id),
                        item.payload_hash,
                        event_fingerprint,
                        metadata_json,
                        None,
                    )
                )

                fragments = _split_searchable_fragments(parsed.fragments)
                for unit_index, fragment in enumerate(fragments):
                    text = _postgres_text(fragment.text) or ""
                    fragment_hash = stable_hash(text)
                    contents.setdefault(fragment_hash, (text, len(text)))
                    unit_key = stable_hash(
                        f"{event_key}\0{unit_index}\0{fragment_hash}\0{fragment.kind}"
                    )
                    text_units.append(
                        (
                            unit_key,
                            event_key,
                            fragment_hash,
                            unit_index,
                            fragment.kind,
                            _postgres_text(fragment.label),
                            fragment.is_error,
                        )
                    )

                seen_artifacts: set[tuple[str, str, str | None]] = set()
                for artifact in parsed.artifacts:
                    artifact_value = _postgres_text(artifact.value) or ""
                    artifact_label = _postgres_text(artifact.label)
                    value_hash = stable_hash(artifact_value)
                    identity = (artifact.kind, value_hash, artifact_label)
                    if identity in seen_artifacts:
                        continue
                    seen_artifacts.add(identity)
                    artifact_key = stable_hash(
                        f"{event_key}\0{artifact.kind}\0{value_hash}\0{artifact_label or ''}"
                    )
                    artifacts.append(
                        (
                            artifact_key,
                            event_key,
                            artifact.kind,
                            artifact_label,
                            artifact_value,
                            value_hash,
                        )
                    )

        self._prepare_staging(connection)
        self._copy_staging(
            connection,
            sessions=sessions,
            contents=contents,
            events=events,
            text_units=text_units,
            artifacts=artifacts,
        )
        self._merge_staging(connection)
        return _ProjectionBatchResult(
            events=len(events),
            text_units=len(text_units),
            artifacts=len(artifacts),
            parse_errors=parse_errors,
        )

    @staticmethod
    def _prepare_staging(connection: Session) -> None:
        connection.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS session_sync_stage (
                session_key text PRIMARY KEY, provider text NOT NULL, external_id text NOT NULL,
                project text, cwd text, observed_at timestamptz, parent_session_id text,
                metadata_json jsonb NOT NULL, machine_id uuid, contributor_id bigint
            ) ON COMMIT DELETE ROWS;
            CREATE TEMP TABLE IF NOT EXISTS content_sync_stage (
                content_hash text PRIMARY KEY, text text NOT NULL, char_count bigint NOT NULL
            ) ON COMMIT DELETE ROWS;
            CREATE TEMP TABLE IF NOT EXISTS event_sync_stage (
                event_key text PRIMARY KEY, source_id bigint NOT NULL,
                source_revision_id bigint NOT NULL, raw_record_id bigint NOT NULL,
                projection_index integer NOT NULL, session_key text,
                ordinal bigint NOT NULL, line_no bigint NOT NULL,
                byte_offset bigint NOT NULL, byte_length bigint NOT NULL,
                observed_at timestamptz, event_type text NOT NULL, subtype text, role text,
                provider_event_id text, parent_event_id text, turn_id text,
                content_hash text NOT NULL, event_fingerprint text, metadata_json jsonb NOT NULL,
                parse_error text
            ) ON COMMIT DELETE ROWS;
            CREATE TEMP TABLE IF NOT EXISTS text_unit_sync_stage (
                unit_key text PRIMARY KEY, event_key text NOT NULL, content_hash text NOT NULL,
                unit_index integer NOT NULL, kind text NOT NULL, label text, is_error boolean NOT NULL
            ) ON COMMIT DELETE ROWS;
            CREATE TEMP TABLE IF NOT EXISTS artifact_sync_stage (
                artifact_key text PRIMARY KEY, event_key text NOT NULL, kind text NOT NULL,
                label text, value text NOT NULL, value_hash text NOT NULL
            ) ON COMMIT DELETE ROWS
            """
        )
        connection.execute(
            """
            TRUNCATE session_sync_stage, content_sync_stage, event_sync_stage,
                     text_unit_sync_stage, artifact_sync_stage
            """
        )

    @staticmethod
    def _copy_staging(
        connection: Session,
        *,
        sessions: dict[str, list[Any]],
        contents: dict[str, tuple[str, int]],
        events: list[tuple[Any, ...]],
        text_units: list[tuple[Any, ...]],
        artifacts: list[tuple[Any, ...]],
    ) -> None:
        connection.copy_rows(
            "session_sync_stage",
            (
                "session_key",
                "provider",
                "external_id",
                "project",
                "cwd",
                "observed_at",
                "parent_session_id",
                "metadata_json",
                "machine_id",
                "contributor_id",
            ),
            (tuple(sessions[key]) for key in sorted(sessions)),
        )
        connection.copy_rows(
            "content_sync_stage",
            ("content_hash", "text", "char_count"),
            ((key, *contents[key]) for key in sorted(contents)),
        )
        connection.copy_rows(
            "event_sync_stage",
            (
                "event_key",
                "source_id",
                "source_revision_id",
                "raw_record_id",
                "projection_index",
                "session_key",
                "ordinal",
                "line_no",
                "byte_offset",
                "byte_length",
                "observed_at",
                "event_type",
                "subtype",
                "role",
                "provider_event_id",
                "parent_event_id",
                "turn_id",
                "content_hash",
                "event_fingerprint",
                "metadata_json",
                "parse_error",
            ),
            events,
        )
        connection.copy_rows(
            "text_unit_sync_stage",
            ("unit_key", "event_key", "content_hash", "unit_index", "kind", "label", "is_error"),
            text_units,
        )
        connection.copy_rows(
            "artifact_sync_stage",
            ("artifact_key", "event_key", "kind", "label", "value", "value_hash"),
            artifacts,
        )

    @staticmethod
    def _merge_staging(connection: Session) -> None:
        connection.execute(
            """
            INSERT INTO sessions(
                session_key, provider, external_id, project, cwd, started_at, ended_at,
                parent_session_id, metadata_json, machine_id, contributor_id
            )
            SELECT session_key, provider, external_id, project, cwd, observed_at, observed_at,
                   parent_session_id, metadata_json, machine_id, contributor_id
            FROM session_sync_stage ORDER BY session_key
            ON CONFLICT (session_key) DO UPDATE SET
                project=COALESCE(sessions.project, EXCLUDED.project),
                cwd=COALESCE(sessions.cwd, EXCLUDED.cwd),
                parent_session_id=COALESCE(sessions.parent_session_id, EXCLUDED.parent_session_id),
                metadata_json=CASE
                    WHEN sessions.metadata_json='{}'::jsonb THEN EXCLUDED.metadata_json
                    ELSE sessions.metadata_json
                END,
                updated_at=CURRENT_TIMESTAMP
            """
        )
        connection.execute(
            """
            INSERT INTO contents(content_hash, text, char_count)
            SELECT content_hash, text, char_count FROM content_sync_stage ORDER BY content_hash
            ON CONFLICT (content_hash) DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO events(
                event_key, source_id, source_revision_id, raw_record_id, projection_index,
                session_id, ordinal, line_no, byte_offset, byte_length, timestamp, event_type, subtype,
                role, provider_event_id, parent_event_id, turn_id, content_hash,
                event_fingerprint, metadata_json, parse_error
            )
            SELECT stage.event_key, stage.source_id, stage.source_revision_id,
                   stage.raw_record_id, stage.projection_index, session.id,
                   stage.ordinal, stage.line_no,
                   stage.byte_offset, stage.byte_length, stage.observed_at, stage.event_type,
                   stage.subtype, stage.role, stage.provider_event_id, stage.parent_event_id,
                   stage.turn_id, stage.content_hash, stage.event_fingerprint,
                   stage.metadata_json, stage.parse_error
            FROM event_sync_stage stage
            LEFT JOIN sessions session ON session.session_key=stage.session_key
            ORDER BY stage.event_key
            """
        )
        connection.execute(
            """
            INSERT INTO session_sources(session_id, source_id)
            SELECT DISTINCT session.id, stage.source_id
            FROM event_sync_stage stage
            JOIN sessions session ON session.session_key=stage.session_key
            ON CONFLICT DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO text_units(
                unit_key, event_id, content_id, unit_index, kind, label, is_error
            )
            SELECT stage.unit_key, event.id, content.id, stage.unit_index,
                   stage.kind, stage.label, stage.is_error
            FROM text_unit_sync_stage stage
            JOIN events event ON event.event_key=stage.event_key
            JOIN contents content ON content.content_hash=stage.content_hash
            ORDER BY stage.unit_key
            """
        )
        connection.execute(
            """
            INSERT INTO artifacts(artifact_key, event_id, kind, label, value, value_hash)
            SELECT stage.artifact_key, event.id, stage.kind, stage.label,
                   stage.value, stage.value_hash
            FROM artifact_sync_stage stage
            JOIN events event ON event.event_key=stage.event_key
            ORDER BY stage.artifact_key
            ON CONFLICT (artifact_key) DO NOTHING
            """
        )


class Ingestor:
    def __init__(
        self,
        settings: Settings,
        adapters: Iterable[ProviderAdapter],
        *,
        batch_lines: int = 1000,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.settings = settings
        self.adapters = {adapter.name: adapter for adapter in adapters}
        self.batch_lines = batch_lines
        self.progress = progress or (lambda _: None)
        self._raw_retention = RawRetentionPolicy(settings.raw_reasoning_retention)
        self._session_cache: dict[str, SessionCacheEntry] = {}
        self._content_cache: dict[str, int] = {}
        self._batch_content_cache: dict[str, int] = {}
        self._contributor_id: int | None = None

    def run(
        self,
        *,
        providers: set[str] | None = None,
        force: bool = False,
        shard_index: int = 0,
        shard_count: int = 1,
        history_since: date | str | None = None,
        history_until: date | str | None = None,
    ) -> IngestSummary:
        return self._run_shard(
            providers=providers,
            force=force,
            shard_index=shard_index,
            shard_count=shard_count,
            finalize=True,
            history_since=history_since,
            history_until=history_until,
        )

    def _run_shard(
        self,
        *,
        providers: set[str] | None,
        force: bool,
        shard_index: int,
        shard_count: int,
        finalize: bool,
        history_since: date | str | None = None,
        history_until: date | str | None = None,
    ) -> IngestSummary:
        if shard_count < 1 or not 0 <= shard_index < shard_count:
            raise ValueError("shard_index must be between zero and shard_count minus one")
        self.settings.ensure_output_dirs()
        scope = HistoryScope(history_since, history_until)
        selection: SourceSelectionPreview | None = None
        if scope.active:
            selection = self.discover_selection(providers=providers, scope=scope)
            sources = list(selection.included_sources)
        else:
            sources = self.discover(providers=providers)
        if shard_count > 1:
            sources = [
                source
                for source in sources
                if int(
                    stable_hash(
                        f"{source.provider}\0{source.source_kind}\0{source.path}"
                    )[:16],
                    16,
                )
                % shard_count
                == shard_index
            ]
        summary = IngestSummary(discovered_files=len(sources))
        if selection is not None:
            summary.excluded_files = selection.excluded_files
            summary.exact_files = selection.exact_files
            summary.mtime_bound_files = selection.mtime_bound_files
            summary.aggregate_files = selection.aggregate_files
            summary.unbounded_files = selection.unbounded_files
        with database(self.settings.database_url) as connection:
            self._register_machine_and_contributor(connection)
            # Every worker registers the same machine and contributor. Release those
            # two row locks before source work so parallel startup cannot convoy
            # behind whichever shard happens to process the slowest first source.
            connection.commit()
            source_snapshots = self._load_source_snapshots(connection)
            skipped_source_ids: list[int] = []
            for index, source in enumerate(sources, start=1):
                adapter = self.adapters[source.provider]
                self.progress(f"[{index}/{len(sources)}] {source.provider}: {source.path}")
                source_key = (source.provider, source.source_kind, str(source.path))
                source_row = source_snapshots.get(source_key)
                if not force and self._source_is_unchanged(source, source_row):
                    summary.skipped_files += 1
                    assert source_row is not None
                    skipped_source_ids.append(int(source_row["source_id"]))
                    continue
                lock_identity = (
                    f"source:{self.settings.machine_id}:{source.provider}:"
                    f"{source.source_kind}:{source.path}"
                )
                with connection.advisory_lock(lock_identity):
                    for attempt in range(5):
                        outcome = self._ingest_source(
                            connection,
                            source,
                            adapter,
                            force=force and attempt == 0,
                            source_row=source_row,
                        )
                        if not outcome["retryable"] or attempt == 4:
                            break
                        # Source/revision setup commits before batch ingestion. If a
                        # later batch deadlocks, reload that durable checkpoint rather
                        # than retrying with the stale pre-attempt snapshot.
                        source_row = self._load_source_snapshots(connection).get(source_key)
                        delay = 0.05 * (2**attempt)
                        self.progress(
                            f"  retrying transient database conflict "
                            f"({attempt + 1}/4) after {delay:.2f}s"
                        )
                        time.sleep(delay)
                summary.processed_files += int(outcome["processed"])
                summary.skipped_files += int(outcome["skipped"])
                summary.reparsed_files += int(outcome["reparsed"])
                summary.events += outcome["events"]
                summary.text_units += outcome["text_units"]
                summary.artifacts += outcome["artifacts"]
                summary.parse_errors += outcome["parse_errors"]
                summary.bytes_read += outcome["bytes_read"]
            if skipped_source_ids:
                connection.execute(
                    "UPDATE sources SET updated_at=clock_timestamp() WHERE id=ANY(?)",
                    (skipped_source_ids,),
                )
            if finalize:
                self._finalize(connection)
        return summary

    def _load_source_snapshots(
        self, connection: Session
    ) -> dict[tuple[str, str, str], Row]:
        rows = connection.execute(
            """
            SELECT s.id AS source_id, s.provider, s.source_kind, s.path,
                   s.active_revision_id AS revision_id, r.size_bytes, r.mtime_ns,
                   r.parser_version, r.status, r.ingested_offset, r.ingested_lines,
                   r.head_hash, r.checkpoint_hash, r.aggregate_hash, r.error_count,
                   r.pending_length, r.pending_hash, r.provenance_json
            FROM sources s
            LEFT JOIN source_revisions r ON r.id=s.active_revision_id
            WHERE s.machine_id=?
            """,
            (self.settings.machine_id,),
        ).fetchall()
        return {
            (str(row["provider"]), str(row["source_kind"]), str(row["path"])): row
            for row in rows
        }

    @staticmethod
    def _source_is_unchanged(source: SourceSpec, source_row: Row | None) -> bool:
        if source_row is None or source_row["status"] != "complete":
            return False
        try:
            stat = source.path.stat()
        except OSError:
            return False
        return (
            int(source_row["size_bytes"]) == stat.st_size
            and int(source_row["mtime_ns"]) == stat.st_mtime_ns
            and (source_row.get("provenance_json") or {}) == source.provenance
        )

    def _finalize(self, connection: Session) -> None:
        self._reconcile_sessions(connection)
        self._prune_orphan_contents(connection)
        connection.commit()
        rebuild_registry(connection)
        apply_contributor_rules(connection)

    def discover(
        self,
        *,
        providers: set[str] | None = None,
        history_since: date | str | None = None,
        history_until: date | str | None = None,
    ) -> list[SourceSpec]:
        """Discover and optionally scope sources without opening their contents."""

        scope = HistoryScope(history_since, history_until)
        return list(self.discover_selection(providers=providers, scope=scope).included_sources)

    def discover_selection(
        self,
        *,
        providers: set[str] | None = None,
        scope: HistoryScope | None = None,
    ) -> SourceSelectionPreview:
        """Return a read-only source selection preview for setup and sync callers."""

        sources: list[SourceSpec] = []
        for name, adapter in self.adapters.items():
            if providers and name not in providers:
                continue
            sources.extend(adapter.discover())
        if self.settings.raw_reasoning_retention != "preserve":
            sources = [self._source_with_retention_provenance(source) for source in sources]
        return preview_source_selection(sources, scope=scope or HistoryScope())

    def _source_with_retention_provenance(self, source: SourceSpec) -> SourceSpec:
        """Make a changed raw-retention choice produce a distinct source revision."""

        if source.provider != "codex":
            return source
        return SourceSpec(
            provider=source.provider,
            path=source.path,
            source_kind=source.source_kind,
            provenance={
                **source.provenance,
                "raw_reasoning_retention": self.settings.raw_reasoning_retention,
            },
        )

    def rebuild_from_archive(self) -> IngestSummary:
        """Regenerate parsed projections using only hash-verified PostgreSQL raw records."""

        summary = IngestSummary()
        with database(self.settings.database_url) as connection:
            self._register_machine_and_contributor(connection)
            # Human annotations use stable target keys and remain. Event and episode
            # tables are disposable projections and are rebuilt below.
            connection.execute("DELETE FROM timesheet_snapshots")
            # A row-wise DELETE is prohibitively expensive at archive scale because
            # canonical_event_id uses ON DELETE SET NULL and every dependent projection
            # must fire its foreign-key action.  These tables are explicitly disposable,
            # so reset the complete dependency graph in one PostgreSQL operation.
            connection.execute("TRUNCATE events CASCADE")
            connection.execute("UPDATE semantic_runs SET status='stale', is_active=false")
            connection.execute("UPDATE sessions SET event_count=0, text_unit_count=0")
            connection.commit()
            summary.discovered_files = int(
                connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            )
            position = (0, 0, 0)
            while rows := connection.execute(
                """
                SELECT raw.id AS raw_record_id, raw.source_revision_id,
                       raw.line_no, raw.byte_offset, raw.byte_length, raw.payload_hash,
                       payload.payload, source.id AS source_id, source.provider,
                       source.path, source.source_kind, revision.revision_no,
                       revision.provenance_json
                FROM raw_records raw
                JOIN raw_payloads payload ON payload.payload_hash=raw.payload_hash
                JOIN source_revisions revision ON revision.id=raw.source_revision_id
                JOIN sources source ON source.id=revision.source_id
                WHERE (source.id, revision.revision_no, raw.line_no) > (?, ?, ?)
                ORDER BY source.id, revision.revision_no, raw.line_no
                LIMIT ?
                """,
                (*position, self.batch_lines),
            ).fetchall():
                self._batch_content_cache.clear()
                canonical_batch: list[int] = []
                for row in rows:
                    counts = self._rebuild_raw_record(connection, row)
                    summary.events += counts.events
                    summary.text_units += counts.text_units
                    summary.artifacts += counts.artifacts
                    summary.parse_errors += counts.parse_errors
                    canonical_batch.append(int(row["raw_record_id"]))
                self._canonicalize_raw_records(connection, canonical_batch)
                position = (
                    int(rows[-1]["source_id"]),
                    int(rows[-1]["revision_no"]),
                    int(rows[-1]["line_no"]),
                )
                connection.commit()
                if summary.events % max(self.batch_lines * 20, 100_000) < self.batch_lines:
                    self.progress(f"  rebuilt {summary.events:,} archived records")
            self._reconcile_sessions(connection)
            self._prune_orphan_contents(connection)
            connection.commit()
            rebuild_registry(connection)
            apply_contributor_rules(connection)
        summary.processed_files = summary.discovered_files
        return summary

    def _rebuild_raw_record(self, connection: Session, row: Row) -> _ProjectionBatchResult:
        raw_line = bytes(row["payload"])
        actual = stable_hash(raw_line)
        if actual != row["payload_hash"] or len(raw_line) != int(row["byte_length"]):
            raise DatabaseError(f"raw archive hash mismatch at raw record {row['raw_record_id']}")
        source = SourceSpec(
            row["provider"],
            Path(row["path"]),
            row["source_kind"],
            row["provenance_json"] or {},
        )
        adapter = self.adapters.get(source.provider)
        if adapter is None:
            raise DatabaseError(f"no provider adapter for archived source {source.provider}")
        try:
            data = orjson.loads(raw_line)
            parsed_records = adapter.parse_many(data, source)
            if not parsed_records:
                raise ValueError("provider returned no projected records")
        except Exception as exc:
            text_units, artifacts, _ = self._insert_parse_error(
                connection,
                source_id=int(row["source_id"]),
                revision_id=int(row["source_revision_id"]),
                raw_record_id=int(row["raw_record_id"]),
                source=source,
                line_no=int(row["line_no"]),
                byte_offset=int(row["byte_offset"]),
                byte_length=int(row["byte_length"]),
                content_hash=row["payload_hash"],
                error=f"{type(exc).__name__}: {exc}",
            )
            return _ProjectionBatchResult(1, text_units, artifacts, 1)
        text_units = 0
        artifacts = 0
        for record_index, parsed in enumerate(parsed_records):
            record_text_units, record_artifacts, _ = self._insert_record(
                connection,
                source_id=int(row["source_id"]),
                revision_id=int(row["source_revision_id"]),
                raw_record_id=int(row["raw_record_id"]),
                source=source,
                parsed=parsed,
                line_no=int(row["line_no"]),
                byte_offset=int(row["byte_offset"]),
                byte_length=int(row["byte_length"]),
                content_hash=row["payload_hash"],
                record_index=record_index,
                record_count=len(parsed_records),
            )
            text_units += record_text_units
            artifacts += record_artifacts
        return _ProjectionBatchResult(len(parsed_records), text_units, artifacts, 0)

    def _register_machine_and_contributor(self, connection: Session) -> None:
        connection.execute(
            """
            INSERT INTO machines(id, name) VALUES (?, ?)
            ON CONFLICT (id) DO UPDATE
            SET name=EXCLUDED.name, last_seen_at=clock_timestamp()
            """,
            (self.settings.machine_id, self.settings.machine_name),
        )
        if not self.settings.contributor:
            self._contributor_id = None
            return
        contributor_key = stable_hash(self.settings.contributor.strip().casefold())
        row = connection.execute(
            """
            INSERT INTO contributors(contributor_key, display_name)
            VALUES (?, ?)
            ON CONFLICT (contributor_key) DO UPDATE
            SET display_name=EXCLUDED.display_name, updated_at=clock_timestamp()
            RETURNING id
            """,
            (contributor_key, self.settings.contributor.strip()),
        ).fetchone()
        assert row is not None
        self._contributor_id = int(row["id"])

    def _ingest_source(
        self,
        connection: Session,
        source: SourceSpec,
        adapter: ProviderAdapter,
        *,
        force: bool,
        source_row: Row | None,
    ) -> dict[str, int | bool]:
        result: dict[str, int | bool] = {
            "processed": False,
            "skipped": False,
            "reparsed": False,
            "events": 0,
            "text_units": 0,
            "artifacts": 0,
            "parse_errors": 0,
            "bytes_read": 0,
            "retryable": False,
        }
        try:
            stat = source.path.stat()
        except OSError as exc:
            self.progress(f"  unavailable: {exc}")
            return result

        document_source = adapter.record_format(source) == "json-document"
        provenance_matches = (
            source_row is None
            or (source_row.get("provenance_json") or {}) == source.provenance
        )
        head_hash = _file_region_hash(source.path, 0, min(stat.st_size, 65_536))
        start_offset = 0
        start_line = 0
        new_revision = force
        if source_row is not None and not force:
            unchanged = (
                source_row["size_bytes"] == stat.st_size
                and source_row["mtime_ns"] == stat.st_mtime_ns
                and source_row["status"] == "complete"
                and provenance_matches
            )
            if unchanged:
                connection.execute(
                    "UPDATE sources SET updated_at=clock_timestamp() WHERE id=?",
                    (source_row["source_id"],),
                )
                connection.commit()
                result["skipped"] = True
                return result
            if document_source:
                aggregate_hash = _file_region_hash(source.path, 0, stat.st_size)
                pending_matches = (
                    source_row["status"] == "partial"
                    and int(source_row["ingested_offset"]) == 0
                    and int(source_row.get("pending_length") or 0) == stat.st_size
                    and source_row.get("pending_hash") == aggregate_hash
                    and provenance_matches
                )
                if pending_matches:
                    new_revision = False
                elif source_row.get("aggregate_hash") == aggregate_hash and provenance_matches:
                    connection.execute(
                        """
                        UPDATE source_revisions
                        SET size_bytes=?, mtime_ns=?, status='complete', updated_at=clock_timestamp()
                        WHERE id=?
                        """,
                        (stat.st_size, stat.st_mtime_ns, source_row["revision_id"]),
                    )
                    connection.execute(
                        "UPDATE sources SET updated_at=clock_timestamp() WHERE id=?",
                        (source_row["source_id"],),
                    )
                    connection.commit()
                    result["skipped"] = True
                    return result
                else:
                    new_revision = True
            else:
                previous_head_length = min(int(source_row["size_bytes"]), 65_536)
                current_prefix_hash = _file_region_hash(source.path, 0, previous_head_length)
                can_resume = (
                    provenance_matches
                    and 0 <= source_row["ingested_offset"] <= stat.st_size
                    and source_row["head_hash"] == current_prefix_hash
                    and _checkpoint_matches(source.path, source_row)
                )
                if can_resume:
                    start_offset = int(source_row["ingested_offset"])
                    start_line = int(source_row["ingested_lines"])
                else:
                    new_revision = True

        source_id, revision_id = self._upsert_source(
            connection,
            source,
            stat,
            adapter.parser_version,
            head_hash,
            source_row,
            new_revision=new_revision,
        )
        if new_revision:
            start_offset = 0
            start_line = 0
            result["reparsed"] = True

        connection.execute(
            """
            UPDATE source_revisions
            SET status='ingesting', started_at=CURRENT_TIMESTAMP, last_error=NULL,
                size_bytes=?, mtime_ns=?, device=?, inode=?, head_hash=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino, head_hash, revision_id),
        )
        connection.commit()

        line_no = start_line
        last_offset = start_offset
        error_count = int(source_row["error_count"] or 0) if source_row and not new_revision else 0
        try:
            document_pending = False
            if document_source:
                raw_document = source.path.read_bytes()
                observed_stat = source.path.stat()
                stable_read = (
                    observed_stat.st_size == stat.st_size
                    and observed_stat.st_mtime_ns == stat.st_mtime_ns
                    and len(raw_document) == observed_stat.st_size
                )
                result["bytes_read"] += len(raw_document)
                try:
                    if stable_read:
                        orjson.loads(raw_document)
                    valid_json = stable_read
                except orjson.JSONDecodeError:
                    valid_json = False
                if not valid_json:
                    document_pending = True
                else:
                    line_no = 1
                    last_offset = len(raw_document)
                    error_count += self._process_batch(
                        connection,
                        source_id=source_id,
                        revision_id=revision_id,
                        source=source,
                        adapter=adapter,
                        batch=[RawLine(1, 0, raw_document, stable_hash(raw_document))],
                        result=result,
                    )
            else:
                with source.path.open("rb") as handle:
                    handle.seek(start_offset)
                    batch: list[RawLine] = []
                    while True:
                        byte_offset = handle.tell()
                        raw_line = handle.readline()
                        if not raw_line:
                            break
                        # An actively-written final line is left for the next run.
                        if not raw_line.endswith(b"\n"):
                            handle.seek(byte_offset)
                            break
                        line_no += 1
                        last_offset = handle.tell()
                        result["bytes_read"] += len(raw_line)
                        batch.append(RawLine(line_no, byte_offset, raw_line, stable_hash(raw_line)))
                        if len(batch) >= self.batch_lines:
                            error_count += self._process_batch(
                                connection,
                                source_id=source_id,
                                revision_id=revision_id,
                                source=source,
                                adapter=adapter,
                                batch=batch,
                                result=result,
                            )
                            self._checkpoint(
                                connection,
                                source.path,
                                revision_id,
                                last_offset,
                                line_no,
                                error_count,
                                status="ingesting",
                            )
                            connection.commit()
                            batch = []
                    if batch:
                        error_count += self._process_batch(
                            connection,
                            source_id=source_id,
                            revision_id=revision_id,
                            source=source,
                            adapter=adapter,
                            batch=batch,
                            result=result,
                        )
            final_stat = source.path.stat()
            status = (
                "partial"
                if document_source and document_pending
                else "complete"
                if last_offset == final_stat.st_size
                else "partial"
            )
            pending_length = (
                final_stat.st_size
                if document_source and document_pending
                else max(final_stat.st_size - last_offset, 0)
            )
            pending_hash = (
                _file_region_hash(
                    source.path,
                    0 if document_source and document_pending else last_offset,
                    pending_length,
                )
                if pending_length
                else None
            )
            self._checkpoint(
                connection,
                source.path,
                revision_id,
                last_offset,
                line_no,
                error_count,
                status=status,
                size_bytes=final_stat.st_size,
                mtime_ns=final_stat.st_mtime_ns,
                pending_length=pending_length,
                pending_hash=pending_hash,
            )
            connection.commit()
            result["processed"] = True
        except (OSError, psycopg.Error, DatabaseError) as exc:
            connection.rollback()
            # IDs inserted by the aborted transaction are not durable. Never let a
            # later source reuse transaction-local cache entries after rollback.
            self._session_cache.clear()
            self._content_cache.clear()
            self._batch_content_cache.clear()
            result["retryable"] = isinstance(
                exc,
                (psycopg.errors.DeadlockDetected, psycopg.errors.SerializationFailure),
            )
            connection.execute(
                """
                UPDATE source_revisions
                SET status='failed', last_error=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (f"{type(exc).__name__}: {exc}", revision_id),
            )
            connection.commit()
            self.progress(f"  failed: {exc}")
        return result

    def _upsert_source(
        self,
        connection: Session,
        source: SourceSpec,
        stat: Any,
        parser_version: int,
        head_hash: str,
        existing: Row | None,
        *,
        new_revision: bool,
    ) -> tuple[int, int]:
        if existing is None:
            row = connection.execute(
                """
                INSERT INTO sources(machine_id, provider, path, source_kind)
                VALUES (?, ?, ?, ?)
                RETURNING id
                """,
                (
                    self.settings.machine_id,
                    source.provider,
                    str(source.path),
                    source.source_kind,
                ),
            ).fetchone()
            assert row is not None
            source_id = int(row["id"])
            revision_no = 1
            new_revision = True
        else:
            source_id = int(existing["source_id"])
            if not new_revision:
                return source_id, int(existing["revision_id"])
            previous_status = "truncated" if stat.st_size < int(existing["size_bytes"] or 0) else "replaced"
            connection.execute(
                """
                UPDATE source_revisions
                SET status=?, closed_at=clock_timestamp(), updated_at=clock_timestamp()
                WHERE id=?
                """,
                (previous_status, existing["revision_id"]),
            )
            revision_no = int(
                connection.execute(
                    "SELECT COALESCE(MAX(revision_no), 0) + 1 FROM source_revisions WHERE source_id=?",
                    (source_id,),
                ).fetchone()[0]
            )

        row = connection.execute(
            """
            INSERT INTO source_revisions(
                source_id, revision_no, size_bytes, mtime_ns, device, inode,
                parser_version, head_hash, provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                source_id,
                revision_no,
                stat.st_size,
                stat.st_mtime_ns,
                stat.st_dev,
                stat.st_ino,
                parser_version,
                head_hash,
                _postgres_json(source.provenance),
            ),
        ).fetchone()
        assert row is not None
        revision_id = int(row["id"])
        connection.execute(
            """
            UPDATE sources SET active_revision_id=?, updated_at=clock_timestamp()
            WHERE id=?
            """,
            (revision_id, source_id),
        )
        connection.commit()
        return source_id, revision_id

    def _process_batch(
        self,
        connection: Session,
        *,
        source_id: int,
        revision_id: int,
        source: SourceSpec,
        adapter: ProviderAdapter,
        batch: list[RawLine],
        result: dict[str, int | bool],
    ) -> int:
        batch = self._apply_raw_retention(source, batch)
        raw_ids = self._archive_raw_batch(connection, revision_id=revision_id, batch=batch)
        self._batch_content_cache.clear()
        errors = 0
        parsed_items: list[tuple[RawLine, list[ParsedRecord] | None, str | None]] = []
        for item in batch:
            try:
                data = orjson.loads(item.payload)
                parsed = adapter.parse_many(data, source)
                if not parsed:
                    raise ValueError("provider returned no projected records")
            except Exception as exc:  # one bad source record must not hide the rest
                parsed_items.append((item, None, f"{type(exc).__name__}: {exc}"))
            else:
                parsed_items.append((item, parsed, None))
        counts = _ProjectionBatchWriter(self.settings, self._contributor_id).persist(
            connection,
            source_id=source_id,
            revision_id=revision_id,
            source=source,
            raw_ids=raw_ids,
            parsed_items=parsed_items,
        )
        errors += counts.parse_errors
        result["events"] = int(result["events"]) + counts.events
        result["text_units"] = int(result["text_units"]) + counts.text_units
        result["artifacts"] = int(result["artifacts"]) + counts.artifacts
        result["parse_errors"] = int(result["parse_errors"]) + counts.parse_errors
        self._canonicalize_raw_records(connection, raw_ids.values())
        return errors

    def _apply_raw_retention(
        self,
        source: SourceSpec,
        batch: list[RawLine],
    ) -> list[RawLine]:
        """Return the exact or explicitly redacted bytes stored for a source batch.

        Redaction is limited to Codex reasoning records and happens before raw
        persistence. Source byte offsets and revision checkpoints still refer to the
        read-only input file; the stored payload hash and byte length describe the
        retained representation used for deterministic replay.
        """

        if source.provider != "codex" or self._raw_retention.mode == "preserve":
            return batch
        retained: list[RawLine] = []
        for item in batch:
            try:
                decoded = orjson.loads(item.payload)
            except orjson.JSONDecodeError:
                retained.append(item)
                continue
            result = self._raw_retention.apply(decoded)
            if result.redacted_records == 0:
                retained.append(item)
                continue
            ending = b"\n" if item.payload.endswith(b"\n") else b""
            payload = orjson.dumps(result.value, option=orjson.OPT_SORT_KEYS) + ending
            retained.append(
                RawLine(
                    line_no=item.line_no,
                    byte_offset=item.byte_offset,
                    payload=payload,
                    payload_hash=stable_hash(payload),
                )
            )
        return retained

    def _preload_batch_projections(
        self, connection: Session, parsed_records: list[ParsedRecord]
    ) -> None:
        sessions = {
            stable_hash(f"{parsed.provider}\0{parsed.session_external_id}"): parsed
            for parsed in parsed_records
            if parsed.session_external_id
        }
        for session_key in sorted(sessions):
            self._upsert_session(connection, sessions[session_key])

        contents: dict[str, str] = {}
        for parsed in parsed_records:
            for fragment in _split_searchable_fragments(parsed.fragments):
                text = _postgres_text(fragment.text) or ""
                contents.setdefault(stable_hash(text), text)
        for content_hash in sorted(contents):
            self._upsert_content(connection, contents[content_hash])

    @staticmethod
    def _archive_raw_batch(
        connection: Session,
        *,
        revision_id: int,
        batch: list[RawLine],
    ) -> dict[int, int]:
        connection.execute(
            """
            CREATE TEMP TABLE IF NOT EXISTS raw_sync_stage (
                source_revision_id bigint NOT NULL,
                line_no bigint NOT NULL,
                byte_offset bigint NOT NULL,
                byte_length bigint NOT NULL,
                payload_hash text NOT NULL,
                payload bytea NOT NULL,
                PRIMARY KEY (source_revision_id, line_no)
            ) ON COMMIT DELETE ROWS
            """
        )
        connection.execute("TRUNCATE raw_sync_stage")
        connection.copy_rows(
            "raw_sync_stage",
            (
                "source_revision_id",
                "line_no",
                "byte_offset",
                "byte_length",
                "payload_hash",
                "payload",
            ),
            (
                (
                    revision_id,
                    item.line_no,
                    item.byte_offset,
                    len(item.payload),
                    item.payload_hash,
                    item.payload,
                )
                for item in batch
            ),
        )
        # PostgreSQL otherwise assumes the freshly loaded temporary table has about
        # 1,000 rows and may repeatedly hash-scan the multi-million-row archive.
        connection.execute("ANALYZE raw_sync_stage")
        connection.execute(
            """
            INSERT INTO raw_payloads(payload_hash, payload, byte_length)
            SELECT DISTINCT ON (payload_hash) payload_hash, payload, byte_length
            FROM raw_sync_stage WHERE true ORDER BY payload_hash
            ON CONFLICT (payload_hash) DO NOTHING
            """
        )
        mismatch = connection.execute(
            """
            SELECT stage.line_no
            FROM raw_sync_stage stage
            WHERE EXISTS (
                SELECT 1 FROM raw_payloads payload
                WHERE payload.payload_hash=stage.payload_hash
                  AND (payload.byte_length<>stage.byte_length
                       OR payload.payload<>stage.payload)
            ) OR EXISTS (
                SELECT 1 FROM raw_records raw
                WHERE raw.source_revision_id=stage.source_revision_id
                  AND raw.line_no=stage.line_no
                  AND (raw.payload_hash<>stage.payload_hash
                       OR raw.byte_offset<>stage.byte_offset
                       OR raw.byte_length<>stage.byte_length)
            )
            LIMIT 1
            """
        ).fetchone()
        if mismatch is not None:
            raise DatabaseError(
                f"immutable raw archive mismatch at revision {revision_id}, line {mismatch['line_no']}"
            )
        connection.execute(
            """
            INSERT INTO raw_records(
                source_revision_id, line_no, byte_offset, byte_length, payload_hash
            )
            SELECT source_revision_id, line_no, byte_offset, byte_length, payload_hash
            FROM raw_sync_stage WHERE true
            ON CONFLICT (source_revision_id, line_no) DO NOTHING
            """
        )
        rows = connection.execute(
            """
            SELECT raw.line_no, raw.id
            FROM raw_records raw
            JOIN raw_sync_stage stage
              ON stage.source_revision_id=raw.source_revision_id
             AND stage.line_no=raw.line_no
            """
        ).fetchall()
        if len(rows) != len(batch):
            raise DatabaseError(
                f"raw archive batch coverage mismatch: expected {len(batch)}, stored {len(rows)}"
            )
        return {int(row["line_no"]): int(row["id"]) for row in rows}

    def _insert_record(
        self,
        connection: Session,
        *,
        source_id: int,
        revision_id: int,
        raw_record_id: int,
        source: SourceSpec,
        parsed: ParsedRecord,
        line_no: int,
        byte_offset: int,
        byte_length: int,
        content_hash: str,
        record_index: int = 0,
        record_count: int = 1,
    ) -> tuple[int, int, bool]:
        session_id = None
        if parsed.session_external_id:
            session_id = self._upsert_session(connection, parsed)
            connection.execute(
                """
                INSERT INTO session_sources(session_id, source_id) VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                (session_id, source_id),
            )
        event_key = _event_key(
            source.provider,
            revision_id,
            line_no,
            content_hash,
            record_index=record_index,
            record_count=record_count,
        )
        event_ordinal = line_no if record_count == 1 else record_index + 1
        timestamp = normalize_timestamp(parsed.timestamp)
        metadata_json = _postgres_json(parsed.metadata)
        event_fingerprint = parsed_event_fingerprint(source.provider, parsed)
        provider_event_id = parsed.provider_event_id or stable_hash(
            orjson.dumps(
                [
                    "derived-provider-event-v1",
                    source.provider,
                    parsed.session_external_id,
                    timestamp.isoformat() if timestamp else None,
                    parsed.parent_event_id,
                    parsed.turn_id,
                    event_fingerprint,
                ]
            )
        )
        row = connection.execute(
            """
            INSERT INTO events(
                event_key, source_id, source_revision_id, raw_record_id,
                projection_index, session_id, ordinal, line_no, byte_offset,
                byte_length, timestamp, event_type, subtype, role, provider_event_id,
                parent_event_id, turn_id, content_hash, event_fingerprint, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                event_key,
                source_id,
                revision_id,
                raw_record_id,
                record_index,
                session_id,
                event_ordinal,
                line_no,
                byte_offset,
                byte_length,
                timestamp,
                parsed.event_type,
                parsed.subtype,
                parsed.role,
                _postgres_text(provider_event_id),
                _postgres_text(parsed.parent_event_id),
                _postgres_text(parsed.turn_id),
                content_hash,
                event_fingerprint,
                metadata_json,
            ),
        ).fetchone()
        assert row is not None
        event_id = int(row["id"])
        fragments = _split_searchable_fragments(parsed.fragments)
        for unit_index, fragment in enumerate(fragments):
            content_id, fragment_hash = self._upsert_content(connection, fragment.text)
            unit_key = stable_hash(f"{event_key}\0{unit_index}\0{fragment_hash}\0{fragment.kind}")
            connection.execute(
                """
                INSERT INTO text_units(
                    unit_key, event_id, content_id, unit_index, kind, label, is_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit_key,
                    event_id,
                    content_id,
                    unit_index,
                    fragment.kind,
                    _postgres_text(fragment.label),
                    fragment.is_error,
                ),
            )
        artifact_count = 0
        seen_artifacts: set[tuple[str, str, str | None]] = set()
        for artifact in parsed.artifacts:
            artifact_value = _postgres_text(artifact.value) or ""
            artifact_label = _postgres_text(artifact.label)
            value_hash = stable_hash(artifact_value)
            identity = (artifact.kind, value_hash, artifact_label)
            if identity in seen_artifacts:
                continue
            seen_artifacts.add(identity)
            artifact_key = stable_hash(
                f"{event_key}\0{artifact.kind}\0{value_hash}\0{artifact_label or ''}"
            )
            connection.execute(
                """
                INSERT INTO artifacts(
                    artifact_key, event_id, kind, label, value, value_hash
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (artifact_key) DO NOTHING
                """,
                (
                    artifact_key,
                    event_id,
                    artifact.kind,
                    artifact_label,
                    artifact_value,
                    value_hash,
                ),
            )
            artifact_count += 1
        return len(fragments), artifact_count, False

    @staticmethod
    def _canonicalize_raw_records(
        connection: Session, raw_record_ids: Iterable[int]
    ) -> None:
        record_ids = list(raw_record_ids)
        if not record_ids:
            return
        connection.execute(
            """
            WITH matches AS (
                SELECT target.id, MIN(candidate.id) AS canonical_id
                FROM events target
                JOIN events candidate
                  ON candidate.provider_event_id=target.provider_event_id
                 AND candidate.event_fingerprint=target.event_fingerprint
                 AND candidate.id<target.id
                WHERE target.raw_record_id=ANY(?)
                  AND target.provider_event_id IS NOT NULL
                  AND target.event_fingerprint IS NOT NULL
                GROUP BY target.id
            )
            UPDATE events target SET canonical_event_id=matches.canonical_id
            FROM matches WHERE target.id=matches.id
            """,
            (record_ids,),
        )

    def _insert_parse_error(
        self,
        connection: Session,
        *,
        source_id: int,
        revision_id: int,
        raw_record_id: int,
        source: SourceSpec,
        line_no: int,
        byte_offset: int,
        byte_length: int,
        content_hash: str,
        error: str,
    ) -> tuple[int, int, bool]:
        event_key = stable_hash(f"{source.provider}\0{revision_id}\0{line_no}\0{content_hash}")
        connection.execute(
            """
            INSERT INTO events(
                event_key, source_id, source_revision_id, raw_record_id,
                projection_index, ordinal, line_no, byte_offset, byte_length,
                event_type, subtype, content_hash, parse_error
            ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, 'parse-error', 'invalid-record', ?, ?)
            """,
            (
                event_key,
                source_id,
                revision_id,
                raw_record_id,
                line_no,
                line_no,
                byte_offset,
                byte_length,
                content_hash,
                error[:8192],
            ),
        )
        return 0, 0, True

    def _upsert_session(self, connection: Session, parsed: ParsedRecord) -> int:
        external_id = parsed.session_external_id
        assert external_id is not None
        session_key = stable_hash(f"{parsed.provider}\0{external_id}")
        external_id_text = _postgres_text(external_id)
        assert external_id_text is not None
        cached = self._session_cache.get(session_key)
        timestamp = normalize_timestamp(parsed.timestamp)
        metadata_json = _postgres_json(parsed.metadata)
        project = _postgres_text(parsed.project)
        cwd = _postgres_text(parsed.cwd)
        parent_session_id = _postgres_text(parsed.parent_session_external_id)
        if cached is not None:
            needs_enrichment = (
                (cached.project is None and project is not None)
                or (cached.cwd is None and cwd is not None)
                or (cached.parent_session_id is None and parent_session_id is not None)
                or (not cached.has_metadata and metadata_json != "{}")
            )
            if needs_enrichment:
                connection.execute(
                    """
                    UPDATE sessions SET
                        project=COALESCE(project, ?), cwd=COALESCE(cwd, ?),
                        parent_session_id=COALESCE(parent_session_id, ?),
                        metadata_json=CASE WHEN metadata_json='{}' THEN ? ELSE metadata_json END,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (project, cwd, parent_session_id, metadata_json, cached.id),
                )
                cached.project = cached.project or project
                cached.cwd = cached.cwd or cwd
                cached.parent_session_id = cached.parent_session_id or parent_session_id
                cached.has_metadata = cached.has_metadata or metadata_json != "{}"
            return cached.id
        row = connection.execute(
            """
            SELECT id, project, cwd, parent_session_id, metadata_json
            FROM sessions WHERE session_key=?
            """,
            (session_key,),
        ).fetchone()
        if row:
            self._session_cache[session_key] = SessionCacheEntry(
                id=int(row["id"]),
                project=row["project"],
                cwd=row["cwd"],
                parent_session_id=row["parent_session_id"],
                has_metadata=bool(row["metadata_json"]),
            )
            return self._upsert_session(connection, parsed)
        row = connection.execute(
            """
            INSERT INTO sessions(
                session_key, provider, external_id, project, cwd, started_at, ended_at,
                parent_session_id, metadata_json, machine_id, contributor_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (session_key) DO NOTHING
            RETURNING id
            """,
            (
                session_key,
                parsed.provider,
                external_id_text,
                project,
                cwd,
                timestamp,
                timestamp,
                parent_session_id,
                metadata_json,
                self.settings.machine_id,
                self._contributor_id,
            ),
        ).fetchone()
        if row is None:
            existing = connection.execute(
                """
                SELECT id, project, cwd, parent_session_id, metadata_json
                FROM sessions WHERE session_key=?
                """,
                (session_key,),
            ).fetchone()
            assert existing is not None
            self._session_cache[session_key] = SessionCacheEntry(
                id=int(existing["id"]),
                project=existing["project"],
                cwd=existing["cwd"],
                parent_session_id=existing["parent_session_id"],
                has_metadata=bool(existing["metadata_json"]),
            )
            return self._upsert_session(connection, parsed)
        session_id = int(row["id"])
        self._session_cache[session_key] = SessionCacheEntry(
            session_id,
            project,
            cwd,
            parent_session_id,
            metadata_json != "{}",
        )
        return session_id

    def _upsert_content(self, connection: Session, text: str) -> tuple[int, str]:
        text = _postgres_text(text) or ""
        content_hash = stable_hash(text)
        cached = self._batch_content_cache.get(content_hash) or self._content_cache.get(
            content_hash
        )
        if cached is not None:
            return cached, content_hash
        row = connection.execute(
            """
            INSERT INTO contents(content_hash, text, char_count) VALUES (?, ?, ?)
            ON CONFLICT (content_hash) DO NOTHING RETURNING id
            """,
            (content_hash, text, len(text)),
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT id FROM contents WHERE content_hash=?", (content_hash,)
            ).fetchone()
        assert row is not None
        content_id = int(row["id"])
        self._batch_content_cache[content_hash] = content_id
        if len(self._content_cache) < 500_000:
            self._content_cache[content_hash] = content_id
        return content_id, content_hash

    def _checkpoint(
        self,
        connection: Session,
        path: Path,
        source_id: int,
        offset: int,
        line_no: int,
        error_count: int,
        *,
        status: str,
        size_bytes: int | None = None,
        mtime_ns: int | None = None,
        pending_length: int = 0,
        pending_hash: str | None = None,
    ) -> None:
        checkpoint_hash = _file_region_hash(path, max(0, offset - 65_536), min(offset, 65_536))
        aggregate_hash = _file_region_hash(path, 0, offset)
        connection.execute(
            """
            UPDATE source_revisions SET
                ingested_offset=?, ingested_lines=?, error_count=?, checkpoint_hash=?,
                status=?, size_bytes=COALESCE(?, size_bytes), mtime_ns=COALESCE(?, mtime_ns),
                aggregate_hash=COALESCE(?, aggregate_hash),
                pending_offset=CASE WHEN ?>0 THEN ? ELSE NULL END,
                pending_length=?, pending_hash=?,
                completed_at=CASE WHEN ?='complete' THEN CURRENT_TIMESTAMP ELSE completed_at END,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (
                offset,
                line_no,
                error_count,
                checkpoint_hash,
                status,
                size_bytes,
                mtime_ns,
                aggregate_hash,
                pending_length,
                offset,
                pending_length,
                pending_hash,
                status,
                source_id,
            ),
        )

    def _reconcile_sessions(self, connection: Session) -> None:
        connection.execute(
            """
            UPDATE sessions SET
                event_count=(SELECT COUNT(*) FROM events e WHERE e.session_id=sessions.id),
                text_unit_count=(
                    SELECT COUNT(*) FROM text_units t
                    JOIN events e ON e.id=t.event_id
                    WHERE e.session_id=sessions.id
                ),
                started_at=COALESCE(
                    (SELECT MIN(timestamp) FROM events e
                     WHERE e.session_id=sessions.id AND e.timestamp IS NOT NULL),
                    started_at
                ),
                ended_at=COALESCE(
                    (SELECT MAX(timestamp) FROM events e
                     WHERE e.session_id=sessions.id AND e.timestamp IS NOT NULL),
                    ended_at
                ),
                updated_at=CURRENT_TIMESTAMP
            """
        )
        connection.execute(
            "DELETE FROM sessions WHERE event_count=0 AND id NOT IN (SELECT session_id FROM session_sources)"
        )
        for provider, adapter in self.adapters.items():
            rows = connection.execute(
                "SELECT id, project, cwd FROM sessions WHERE provider=?", (provider,)
            ).fetchall()
            updates = []
            for row in rows:
                project = adapter.normalize_project(row["project"])
                cwd = adapter.normalize_project(row["cwd"])
                if project != row["project"] or cwd != row["cwd"]:
                    updates.append((project, cwd, row["id"]))
            if updates:
                connection.executemany(
                    "UPDATE sessions SET project=?, cwd=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    updates,
                )

    def _prune_orphan_contents(self, connection: Session) -> None:
        connection.execute(
            """
            DELETE FROM contents AS content
            WHERE NOT EXISTS (
                SELECT 1 FROM text_units AS unit
                WHERE unit.content_id = content.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM semantic_windows AS semantic_window
                WHERE semantic_window.content_id = content.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM episodes AS episode
                WHERE episode.goal_content_id = content.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM episodes AS episode
                WHERE episode.outcome_content_id = content.id
            )
              AND NOT EXISTS (
                SELECT 1 FROM episodes AS episode
                WHERE episode.document_content_id = content.id
            )
            """
        )


@dataclass(frozen=True, slots=True)
class _WorkerRequest:
    settings: Settings
    providers: tuple[str, ...]
    force: bool
    batch_lines: int
    progress_every: int
    shard_index: int
    shard_count: int
    history_since: date | None
    history_until: date | None


def _configured_adapters(settings: Settings) -> list[ProviderAdapter]:
    from chatreview.providers import ClaudeAdapter, CodexAdapter, GeminiAdapter, GitAdapter

    return [
        CodexAdapter(settings.codex_root),
        ClaudeAdapter(settings.claude_root),
        GeminiAdapter(settings.gemini_root),
        GitAdapter(settings.git_root, settings.git_sources_dir),
    ]


def _prepare_selected_adapters(
    adapters: Iterable[ProviderAdapter], providers: set[str] | None
) -> None:
    for adapter in adapters:
        if providers and adapter.name not in providers:
            continue
        prepare = getattr(adapter, "prepare", None)
        if callable(prepare):
            prepare()


def _worker_progress(request: _WorkerRequest, message: str) -> None:
    if message.startswith("["):
        try:
            position = int(message[1 : message.index("/")])
        except (ValueError, IndexError):
            position = 0
        if position != 1 and position % request.progress_every:
            return
    print(f"[worker {request.shard_index + 1}/{request.shard_count}] {message}", flush=True)


def _run_sync_worker(request: _WorkerRequest) -> IngestSummary:
    close_pools()
    try:
        ingestor = Ingestor(
            request.settings,
            _configured_adapters(request.settings),
            batch_lines=request.batch_lines,
            progress=lambda message: _worker_progress(request, message),
        )
        return ingestor._run_shard(
            providers=set(request.providers) or None,
            force=request.force,
            shard_index=request.shard_index,
            shard_count=request.shard_count,
            finalize=False,
            history_since=request.history_since,
            history_until=request.history_until,
        )
    finally:
        close_pools()


def _merge_summaries(summaries: Iterable[IngestSummary]) -> IngestSummary:
    merged = IngestSummary()
    for summary in summaries:
        merged.discovered_files += summary.discovered_files
        merged.processed_files += summary.processed_files
        merged.skipped_files += summary.skipped_files
        merged.reparsed_files += summary.reparsed_files
        merged.events += summary.events
        merged.text_units += summary.text_units
        merged.artifacts += summary.artifacts
        merged.parse_errors += summary.parse_errors
        merged.bytes_read += summary.bytes_read
        merged.excluded_files = max(merged.excluded_files, summary.excluded_files)
        merged.exact_files = max(merged.exact_files, summary.exact_files)
        merged.mtime_bound_files = max(merged.mtime_bound_files, summary.mtime_bound_files)
        merged.aggregate_files = max(merged.aggregate_files, summary.aggregate_files)
        merged.unbounded_files = max(merged.unbounded_files, summary.unbounded_files)
    return merged


def sync_sources(
    settings: Settings,
    *,
    providers: set[str] | None = None,
    force: bool = False,
    batch_lines: int = 1000,
    progress_every: int = 25,
    workers: int = 1,
    shard_index: int = 0,
    shard_count: int = 1,
    history_since: date | str | None = None,
    history_until: date | str | None = None,
    progress: ProgressCallback | None = None,
) -> IngestSummary:
    """Synchronize sources, owning worker lifecycle and one global finalization pass."""

    if workers < 1:
        raise ValueError("workers must be at least one")
    if workers > 1 and (shard_index != 0 or shard_count != 1):
        raise ValueError("workers cannot be combined with explicit shard options")
    scope = HistoryScope(history_since, history_until)
    report = progress or (lambda _: None)
    adapters = _configured_adapters(settings)
    _prepare_selected_adapters(adapters, providers)
    if workers == 1:
        return Ingestor(
            settings,
            adapters,
            batch_lines=batch_lines,
            progress=report,
        ).run(
            providers=providers,
            force=force,
            shard_index=shard_index,
            shard_count=shard_count,
            history_since=scope.since,
            history_until=scope.until,
        )

    close_pools()
    requests = [
        _WorkerRequest(
            settings=settings,
            providers=tuple(sorted(providers or ())),
            force=force,
            batch_lines=batch_lines,
            progress_every=progress_every,
            shard_index=index,
            shard_count=workers,
            history_since=scope.since,
            history_until=scope.until,
        )
        for index in range(workers)
    ]
    report(f"Starting {workers} deterministic source workers")
    summaries: list[IngestSummary] = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as executor:
        futures = {executor.submit(_run_sync_worker, request): request for request in requests}
        for future in as_completed(futures):
            request = futures[future]
            summaries.append(future.result())
            report(f"Worker {request.shard_index + 1}/{workers} complete")

    finalizer = Ingestor(settings, _configured_adapters(settings), batch_lines=batch_lines)
    with database(settings.database_url) as connection:
        finalizer._register_machine_and_contributor(connection)
        finalizer._finalize(connection)
    return _merge_summaries(summaries)


def _event_key(
    provider: str,
    revision_id: int,
    line_no: int,
    content_hash: str,
    *,
    record_index: int = 0,
    record_count: int = 1,
) -> str:
    identity = f"{provider}\0{revision_id}\0{line_no}\0{content_hash}"
    if record_count > 1:
        identity = f"{identity}\0{record_index}"
    return stable_hash(identity)


def normalize_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return None
    if numeric > 10_000_000_000:
        numeric /= 1000
    try:
        return datetime.fromtimestamp(numeric, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _file_region_hash(path: Path, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    if length <= 0:
        return digest.hexdigest()
    with path.open("rb") as handle:
        handle.seek(offset)
        remaining = length
        while remaining:
            block = handle.read(min(remaining, 65_536))
            if not block:
                break
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def _checkpoint_matches(path: Path, source_row: Row) -> bool:
    offset = int(source_row["ingested_offset"])
    expected = source_row["checkpoint_hash"]
    if not expected:
        return offset == 0
    actual = _file_region_hash(path, max(0, offset - 65_536), min(offset, 65_536))
    return actual == expected


def _postgres_text(value: str | None) -> str | None:
    """Make a parsed projection representable as PostgreSQL text; raw bytea stays exact."""

    return value.replace("\x00", "\ufffd") if value is not None else None


def _postgres_json(value: Any) -> str:
    encoded = orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode()
    return encoded.replace("\\u0000", "\\ufffd")


def _split_searchable_fragments(fragments: Iterable[TextFragment]) -> list[TextFragment]:
    """Keep oversized normalized text complete without exceeding tsvector's 1 MiB limit."""

    result: list[TextFragment] = []
    for fragment in fragments:
        if len(fragment.text) <= MAX_SEARCHABLE_FRAGMENT_CHARS:
            result.append(fragment)
            continue
        for start in range(0, len(fragment.text), MAX_SEARCHABLE_FRAGMENT_CHARS):
            result.append(
                TextFragment(
                    kind=fragment.kind,
                    text=fragment.text[start : start + MAX_SEARCHABLE_FRAGMENT_CHARS],
                    label=fragment.label,
                    is_error=fragment.is_error,
                )
            )
    return result
