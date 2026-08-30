"""Read-only setup discovery for an Open Chat Reviewer installation.

The setup page needs to answer two different questions without mutating the
archive: what is present on this machine, and what would be included if the
operator selected a particular history/semantic policy.  This module keeps
those questions behind a small interface so the API and UI do not need to
know PostgreSQL details.

``SetupPlanner`` deliberately has no write methods.  Source roots are only
inspected with filesystem metadata calls, and the database adapter uses a
read-only transaction.  A ``SetupDatabase`` implementation can be injected in
tests or in another deployment; ``PostgresSetupDatabase`` is the production
adapter for the repository's ``Session``/``database`` seam.
"""

from __future__ import annotations

import ipaddress
import os
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from chatreview.db import database
from chatreview.network import tailscale_identity

SUPPORTED_PROVIDERS = ("codex", "claude", "gemini", "git")
"""Provider names accepted by a setup plan, in the default display order."""

_DATE_FORMAT = "%Y-%m-%d"
_REASONING_MARKERS = (
    '"reasoning"',
    '"thinking"',
    '"analysis"',
    '"encrypted_content"',
)
_ENCRYPTED_MARKERS = ('"encrypted_content"', '"encrypted"', '"signature"')
_OPAQUE_ARTIFACT_KINDS = ("opaque-payload", "opaque_encoded_payload")
_COUNT_TABLES = (
    "sources",
    "source_revisions",
    "raw_records",
    "raw_payloads",
    "sessions",
    "events",
    "contents",
    "text_units",
    "artifacts",
    "episodes",
    "annotations",
)
_STORAGE_TABLES = (
    "raw_payloads",
    "raw_records",
    "events",
    "contents",
    "text_units",
    "artifacts",
    "semantic_windows",
)


class SetupDatabase(Protocol):
    """Local-substitutable read-only database contract for ``SetupPlanner``."""

    def health(self) -> DatabaseHealth:
        """Return only quick database/worker health facts for status polling."""

    def snapshot(self) -> DatabaseSnapshot:
        """Return aggregate facts without returning raw payload or message text."""

    def machines(self) -> tuple[MachineNode, ...]:
        """Return machines that have registered through the shared archive."""

    def estimate_scope(
        self,
        scope: HistoryScope,
        providers: tuple[str, ...],
    ) -> ScopeEstimate:
        """Estimate rows and bytes covered by a validated plan selection."""


class SettingsLike(Protocol):
    """The machine-local settings attributes needed for setup discovery."""

    database_url: str
    machine_id: UUID
    machine_name: str


@dataclass(frozen=True, slots=True)
class HistoryScope:
    """Inclusive calendar-date scope for an ingestion or semantic build.

    ``None`` for both bounds means all available history.  A bounded scope is
    interpreted as an inclusive range by the UI and as a half-open UTC range
    by the PostgreSQL adapter.  Keeping the date (rather than timestamp) in
    the plan matches how an operator normally chooses archive history and
    avoids timezone surprises at the UI boundary.
    """

    start: date | None = None
    end: date | None = None

    def __post_init__(self) -> None:
        if self.start is not None and not isinstance(self.start, date):
            raise TypeError("history start must be a date")
        if self.end is not None and not isinstance(self.end, date):
            raise TypeError("history end must be a date")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("history start date must be on or before the end date")

    @property
    def mode(self) -> Literal["all", "range"]:
        """Return the UI mode represented by this scope."""

        return "all" if self.start is None and self.end is None else "range"

    @classmethod
    def from_values(
        cls,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> HistoryScope:
        """Build a scope from API-friendly ISO date values."""

        return cls(start=_coerce_date(start, "start"), end=_coerce_date(end, "end"))

    def to_dict(self) -> dict[str, str | None]:
        return {
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "mode": self.mode,
        }


@dataclass(frozen=True, slots=True)
class SemanticPolicy:
    """Semantic inclusion choices exposed by setup and map rebuild controls.

    ``include_reasoning`` refers to readable normalized reasoning fragments.
    ``include_encoded_reasoning`` records the operator's explicit choice about
    encrypted/encoded source material, but such bytes are never passed to an
    embedding model as text.  The production semantic builder can use this
    policy to retain a provenance-aware exclusion and the preview can show the
    space impact separately.
    """

    include_reasoning: bool = False
    include_encoded_reasoning: bool = False
    include_tool_calls: bool = True
    include_context_summaries: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "include_reasoning": self.include_reasoning,
            "include_encoded_reasoning": self.include_encoded_reasoning,
            "include_tool_calls": self.include_tool_calls,
            "include_context_summaries": self.include_context_summaries,
        }


@dataclass(frozen=True, slots=True)
class SetupPlan:
    """Validated, side-effect-free selection for a machine setup preview."""

    providers: tuple[str, ...] = SUPPORTED_PROVIDERS
    history: HistoryScope = field(default_factory=HistoryScope)
    semantic: SemanticPolicy = field(default_factory=SemanticPolicy)

    def __post_init__(self) -> None:
        normalized = tuple(dict.fromkeys(str(provider).strip().lower() for provider in self.providers))
        if not normalized:
            raise ValueError("setup plan must select at least one provider")
        unsupported = tuple(provider for provider in normalized if provider not in SUPPORTED_PROVIDERS)
        if unsupported:
            raise ValueError(f"unsupported provider: {', '.join(unsupported)}")
        if normalized != self.providers:
            object.__setattr__(self, "providers", normalized)
        if not isinstance(self.history, HistoryScope):
            raise TypeError("history must be a HistoryScope")
        if not isinstance(self.semantic, SemanticPolicy):
            raise TypeError("semantic must be a SemanticPolicy")

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": list(self.providers),
            "history": self.history.to_dict(),
            "semantic": self.semantic.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MachineIdentity:
    """Non-secret identity information used to explain multi-machine setup."""

    id: str
    name: str
    hostname: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "hostname": self.hostname}


@dataclass(frozen=True, slots=True)
class ProviderRootStatus:
    """Read-only metadata about one machine-local provider root."""

    provider: str
    path: str | None
    history_file: str | None
    exists: bool
    is_directory: bool
    readable: bool
    history_exists: bool | None
    history_bytes: int | None
    issue: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "path": self.path,
            "history_file": self.history_file,
            "exists": self.exists,
            "is_directory": self.is_directory,
            "readable": self.readable,
            "history_exists": self.history_exists,
            "history_bytes": self.history_bytes,
            "issue": self.issue,
        }


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Database and derived-worker state safe for a setup/status response."""

    available: bool
    schema_version: int | None = None
    ingestion_complete: int = 0
    ingestion_in_progress: int = 0
    ingestion_failed: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "schema_version": self.schema_version,
            "ingestion_complete": self.ingestion_complete,
            "ingestion_in_progress": self.ingestion_in_progress,
            "ingestion_failed": self.ingestion_failed,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class CorpusStats:
    """Aggregate corpus counts, dates, and relation storage sizes."""

    database_size_bytes: int | None = None
    table_storage_bytes: Mapping[str, int] = field(default_factory=dict)
    sources: int = 0
    source_revisions: int = 0
    raw_records: int = 0
    raw_payloads: int = 0
    sessions: int = 0
    events: int = 0
    contents: int = 0
    text_units: int = 0
    artifacts: int = 0
    episodes: int = 0
    annotations: int = 0
    parse_errors: int = 0
    source_bytes: int = 0
    indexed_bytes: int = 0
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None
    providers: Mapping[str, int] = field(default_factory=dict)
    source_status: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "database_size_bytes": self.database_size_bytes,
            "table_storage_bytes": dict(self.table_storage_bytes),
            "sources": self.sources,
            "source_revisions": self.source_revisions,
            "raw_records": self.raw_records,
            "raw_payloads": self.raw_payloads,
            "sessions": self.sessions,
            "events": self.events,
            "contents": self.contents,
            "text_units": self.text_units,
            "artifacts": self.artifacts,
            "episodes": self.episodes,
            "annotations": self.annotations,
            "parse_errors": self.parse_errors,
            "source_bytes": self.source_bytes,
            "indexed_bytes": self.indexed_bytes,
            "first_event_at": _iso(self.first_event_at),
            "last_event_at": _iso(self.last_event_at),
            "providers": dict(self.providers),
            "source_status": dict(self.source_status),
        }


@dataclass(frozen=True, slots=True)
class ReasoningFootprint:
    """Space and row counts for readable, encoded, and opaque evidence."""

    raw_reasoning_records: int | None = 0
    raw_reasoning_bytes: int | None = 0
    encrypted_reasoning_records: int | None = 0
    encrypted_reasoning_bytes: int | None = 0
    readable_reasoning_units: int = 0
    readable_reasoning_bytes: int = 0
    opaque_artifact_count: int = 0
    opaque_artifact_bytes: int = 0
    semantic_windows_total: int = 0
    semantic_reasoning_windows: int = 0
    raw_scan_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_reasoning_records": self.raw_reasoning_records,
            "raw_reasoning_bytes": self.raw_reasoning_bytes,
            "encrypted_reasoning_records": self.encrypted_reasoning_records,
            "encrypted_reasoning_bytes": self.encrypted_reasoning_bytes,
            "readable_reasoning_units": self.readable_reasoning_units,
            "readable_reasoning_bytes": self.readable_reasoning_bytes,
            "opaque_artifact_count": self.opaque_artifact_count,
            "opaque_artifact_bytes": self.opaque_artifact_bytes,
            "semantic_windows_total": self.semantic_windows_total,
            "semantic_reasoning_windows": self.semantic_reasoning_windows,
            "raw_scan_complete": self.raw_scan_complete,
        }


@dataclass(frozen=True, slots=True)
class MachineNode:
    """A machine represented in the central archive's topology view."""

    machine_id: str
    name: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    source_count: int = 0
    session_count: int = 0
    event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine_id": self.machine_id,
            "name": self.name,
            "first_seen_at": _iso(self.first_seen_at),
            "last_seen_at": _iso(self.last_seen_at),
            "source_count": self.source_count,
            "session_count": self.session_count,
            "event_count": self.event_count,
        }


@dataclass(frozen=True, slots=True)
class SemanticRunStatus:
    """Safe progress metadata for an existing semantic run."""

    run_key: str
    profile: str
    status: str
    is_active: bool
    expected_count: int
    chunk_count: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_key": self.run_key,
            "profile": self.profile,
            "status": self.status,
            "is_active": self.is_active,
            "expected_count": self.expected_count,
            "chunk_count": self.chunk_count,
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ScopeEstimate:
    """Read-only estimate for a selected date/provider range."""

    available: bool = True
    start: date | None = None
    end: date | None = None
    providers: tuple[str, ...] = ()
    events: int = 0
    sessions: int = 0
    text_units: int = 0
    raw_records: int = 0
    raw_bytes: int = 0
    included_percent: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "providers": list(self.providers),
            "events": self.events,
            "sessions": self.sessions,
            "text_units": self.text_units,
            "raw_records": self.raw_records,
            "raw_bytes": self.raw_bytes,
            "included_percent": self.included_percent,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    """Complete database-side setup facts, with no raw content fields."""

    health: DatabaseHealth
    corpus: CorpusStats = field(default_factory=CorpusStats)
    reasoning: ReasoningFootprint = field(default_factory=ReasoningFootprint)
    machines: tuple[MachineNode, ...] = ()
    semantic_runs: tuple[SemanticRunStatus, ...] = ()


@dataclass(frozen=True, slots=True)
class SetupStatus:
    """Small status response suitable for polling while sync/build runs."""

    generated_at: datetime
    machine: MachineIdentity
    roots: tuple[ProviderRootStatus, ...]
    database: DatabaseHealth

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": _iso(self.generated_at),
            "machine": self.machine.to_dict(),
            "roots": [root.to_dict() for root in self.roots],
            "database": self.database.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MachineDiscovery:
    """Credential-free result of checking the shared archive's machine registry."""

    generated_at: datetime
    current_machine_id: str
    available: bool
    machines: tuple[MachineNode, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        count = len(self.machines)
        return {
            "generated_at": _iso(self.generated_at),
            "current_machine_id": self.current_machine_id,
            "available": self.available,
            "method": "shared_database",
            "network_scan": False,
            "machines": [machine.to_dict() for machine in self.machines],
            "message": (
                f"Checked the shared archive: {count} registered "
                f"machine{'s' if count != 1 else ''}. No network scan was performed."
                if self.available
                else "The shared archive could not be checked. No network scan was performed."
            ),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class SetupConnection:
    """Credential-free addresses and readiness facts for connecting writers."""

    generated_at: datetime
    central_machine: MachineIdentity
    web_url: str
    web_host: str
    web_port: int
    database_local_endpoint: str
    database_writer_endpoint: str | None
    database_remote_ready: bool
    tailscale_connected: bool
    tailscale_ipv4: str | None
    tailscale_dns_name: str | None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": _iso(self.generated_at),
            "central_machine": self.central_machine.to_dict(),
            "web": {
                "url": self.web_url,
                "host": self.web_host,
                "port": self.web_port,
            },
            "database": {
                "local_endpoint": self.database_local_endpoint,
                "writer_endpoint": self.database_writer_endpoint,
                "remote_ready": self.database_remote_ready,
            },
            "tailscale": {
                "connected": self.tailscale_connected,
                "ipv4": self.tailscale_ipv4,
                "dns_name": self.tailscale_dns_name,
            },
            "network_scan": False,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class SetupPreview:
    """Full preview for the setup landing page."""

    generated_at: datetime
    plan: SetupPlan
    machine: MachineIdentity
    roots: tuple[ProviderRootStatus, ...]
    database: DatabaseHealth
    corpus: CorpusStats
    reasoning: ReasoningFootprint
    machines: tuple[MachineNode, ...]
    semantic_runs: tuple[SemanticRunStatus, ...]
    scope_estimate: ScopeEstimate
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": _iso(self.generated_at),
            "plan": self.plan.to_dict(),
            "machine": self.machine.to_dict(),
            "roots": [root.to_dict() for root in self.roots],
            "database": self.database.to_dict(),
            "corpus": self.corpus.to_dict(),
            "reasoning": self.reasoning.to_dict(),
            "machines": [machine.to_dict() for machine in self.machines],
            "semantic_runs": [run.to_dict() for run in self.semantic_runs],
            "scope_estimate": self.scope_estimate.to_dict(),
            "warnings": list(self.warnings),
        }


class SetupPlanner:
    """Compose machine discovery and read-only database facts for setup UI."""

    def __init__(self, settings: SettingsLike, *, database: SetupDatabase | None = None) -> None:
        self.settings = settings
        self.database = database or PostgresSetupDatabase(settings.database_url)

    def preview(self, plan: SetupPlan | None = None) -> SetupPreview:
        """Return a complete, side-effect-free preview for ``plan``."""

        plan = plan or SetupPlan()
        machine = self._machine_identity()
        roots = self._roots()
        snapshot, database_error = self._read_snapshot()
        scope = self._estimate_scope(plan, snapshot, database_error)
        warnings = self._warnings(plan, roots, snapshot, scope, database_error)
        return SetupPreview(
            generated_at=datetime.now(tz=UTC),
            plan=plan,
            machine=machine,
            roots=roots,
            database=snapshot.health,
            corpus=snapshot.corpus,
            reasoning=snapshot.reasoning,
            machines=snapshot.machines,
            semantic_runs=snapshot.semantic_runs,
            scope_estimate=scope,
            warnings=tuple(warnings),
        )

    def status(self) -> SetupStatus:
        """Return current machine roots and database health without an estimate."""

        health_reader = getattr(self.database, "health", None)
        try:
            health = health_reader() if callable(health_reader) else self.database.snapshot().health
            if not isinstance(health, DatabaseHealth):
                raise TypeError("invalid database health")
        except Exception as exc:
            health = DatabaseHealth(available=False, error=_safe_error(exc))
        return SetupStatus(
            generated_at=datetime.now(tz=UTC),
            machine=self._machine_identity(),
            roots=self._roots(),
            database=health,
        )

    def machines(self) -> MachineDiscovery:
        """Check PostgreSQL registrations; this never scans the local network."""

        machine = self._machine_identity()
        try:
            reader = getattr(self.database, "machines", None)
            machines = reader() if callable(reader) else self.database.snapshot().machines
            if not isinstance(machines, tuple) or any(not isinstance(item, MachineNode) for item in machines):
                raise TypeError("invalid machine registry")
            return MachineDiscovery(
                generated_at=datetime.now(tz=UTC),
                current_machine_id=machine.id,
                available=True,
                machines=machines,
            )
        except Exception as exc:
            return MachineDiscovery(
                generated_at=datetime.now(tz=UTC),
                current_machine_id=machine.id,
                available=False,
                error=_safe_error(exc),
            )

    def connection(self) -> SetupConnection:
        """Explain safe central endpoints without exposing database credentials."""

        identity = tailscale_identity()
        tailscale_only = os.environ.get("CHATREVIEW_WEB_TAILSCALE_ONLY", "0") == "1"
        configured_web_host = str(getattr(self.settings, "host", "127.0.0.1"))
        web_port = int(getattr(self.settings, "port", 8765))
        if identity and (tailscale_only or configured_web_host in {"0.0.0.0", "::"}):
            web_host = identity.dns_name
        else:
            web_host = configured_web_host

        parsed = urlsplit(self.settings.database_url)
        query = parse_qs(parsed.query)
        database_host = parsed.hostname or "local-socket"
        database_port = parsed.port or int(query.get("port", [5432])[0])
        bind_host = os.environ.get("CHATREVIEW_DB_BIND_ADDRESS", database_host).strip()
        public_host = os.environ.get("CHATREVIEW_PUBLIC_DATABASE_HOST", "").strip()
        if not public_host and identity and bind_host == identity.ipv4:
            public_host = identity.dns_name
        if not public_host and not _loopback_host(database_host):
            public_host = database_host
        remote_ready = bool(public_host and not _loopback_host(bind_host))
        writer_endpoint = f"{public_host}:{database_port}" if remote_ready else None

        warnings: list[str] = []
        if identity is None:
            warnings.append(
                "Tailscale is not connected on the central machine. "
                "Writers need another private network path."
            )
        if not remote_ready:
            warnings.append(
                "PostgreSQL is local-only. Rebind the bundled database to the "
                "Tailscale address before adding writers."
            )
        return SetupConnection(
            generated_at=datetime.now(tz=UTC),
            central_machine=self._machine_identity(),
            web_url=f"http://{web_host}:{web_port}",
            web_host=web_host,
            web_port=web_port,
            database_local_endpoint=f"{database_host}:{database_port}",
            database_writer_endpoint=writer_endpoint,
            database_remote_ready=remote_ready,
            tailscale_connected=identity is not None,
            tailscale_ipv4=identity.ipv4 if identity else None,
            tailscale_dns_name=identity.dns_name if identity else None,
            warnings=tuple(warnings),
        )

    def _read_snapshot(self) -> tuple[DatabaseSnapshot, str | None]:
        try:
            snapshot = self.database.snapshot()
        except Exception as exc:  # database adapters must not break root discovery
            error = _safe_error(exc)
            return DatabaseSnapshot(health=DatabaseHealth(available=False, error=error)), error
        if not isinstance(snapshot, DatabaseSnapshot):
            error = "invalid database snapshot"
            return DatabaseSnapshot(health=DatabaseHealth(available=False, error=error)), error
        return snapshot, None

    def _estimate_scope(
        self,
        plan: SetupPlan,
        snapshot: DatabaseSnapshot,
        database_error: str | None,
    ) -> ScopeEstimate:
        if database_error or not snapshot.health.available:
            return ScopeEstimate(
                available=False,
                start=plan.history.start,
                end=plan.history.end,
                providers=plan.providers,
                error=database_error or snapshot.health.error or "database unavailable",
            )
        try:
            estimate = self.database.estimate_scope(plan.history, plan.providers)
        except Exception as exc:
            return ScopeEstimate(
                available=False,
                start=plan.history.start,
                end=plan.history.end,
                providers=plan.providers,
                error=_safe_error(exc),
            )
        if not isinstance(estimate, ScopeEstimate):
            return ScopeEstimate(
                available=False,
                start=plan.history.start,
                end=plan.history.end,
                providers=plan.providers,
                error="invalid scope estimate",
            )
        return estimate

    def _machine_identity(self) -> MachineIdentity:
        machine_id = getattr(self.settings, "machine_id", None)
        machine_name = str(getattr(self.settings, "machine_name", "") or platform.node() or "unknown")
        return MachineIdentity(
            id=str(machine_id) if machine_id is not None else "unconfigured",
            name=machine_name,
            hostname=platform.node() or "unknown",
        )

    def _roots(self) -> tuple[ProviderRootStatus, ...]:
        roots: list[ProviderRootStatus] = []
        for provider in SUPPORTED_PROVIDERS:
            root_value = getattr(self.settings, f"{provider}_root", None)
            history_value = getattr(self.settings, f"{provider}_history", None)
            roots.append(_inspect_root(provider, root_value, history_value))
        return tuple(roots)

    @staticmethod
    def _warnings(
        plan: SetupPlan,
        roots: Sequence[ProviderRootStatus],
        snapshot: DatabaseSnapshot,
        scope: ScopeEstimate,
        database_error: str | None,
    ) -> list[str]:
        warnings: list[str] = []
        for root in roots:
            if root.provider in plan.providers and not root.exists:
                warnings.append(f"{root.provider} source root is missing or unconfigured")
            elif root.provider in plan.providers and not root.readable:
                warnings.append(f"{root.provider} source root is not readable")
        if database_error or not snapshot.health.available:
            warnings.append("database facts are unavailable; scope and storage estimates are incomplete")
        if scope.available and scope.events == 0:
            warnings.append("the selected history/provider scope contains no timestamped events")
        if plan.semantic.include_reasoning:
            warnings.append(
                "readable reasoning is selected for semantic vectors; review the footprint before rebuilding"
            )
        if plan.semantic.include_encoded_reasoning:
            warnings.append(
                "encoded reasoning is not human-readable vector text; raw evidence remains "
                "separate from semantic input"
            )
        if not snapshot.reasoning.raw_scan_complete:
            warnings.append(
                "the exact encoded-reasoning footprint is not scanned during status polling; "
                "request a one-off read-only footprint scan before rebuilding"
            )
        return warnings


class PostgresSetupDatabase:
    """Production ``SetupDatabase`` adapter backed by a read-only PostgreSQL session."""

    def __init__(self, database_url: str, *, scan_raw_reasoning: bool = False) -> None:
        self._database_url = database_url
        self._scan_raw_reasoning = scan_raw_reasoning

    def health(self) -> DatabaseHealth:
        """Read quick health metadata without scanning the large raw archive."""

        with database(self._database_url, read_only=True) as connection:
            return self._health(connection)

    def snapshot(self) -> DatabaseSnapshot:
        with database(self._database_url, read_only=True) as connection:
            health = self._health(connection)
            corpus = self._corpus(connection)
            reasoning = self._reasoning(connection, scan_raw_reasoning=self._scan_raw_reasoning)
            machines = self._machines(connection)
            semantic_runs = self._semantic_runs(connection)
        return DatabaseSnapshot(
            health=health,
            corpus=corpus,
            reasoning=reasoning,
            machines=machines,
            semantic_runs=semantic_runs,
        )

    def machines(self) -> tuple[MachineNode, ...]:
        """Read registered machines without computing the full setup preview."""

        with database(self._database_url, read_only=True) as connection:
            return self._machines(connection)

    def estimate_scope(self, scope: HistoryScope, providers: tuple[str, ...]) -> ScopeEstimate:
        clauses, parameters = _event_scope_clause(scope, providers)
        with database(self._database_url, read_only=True) as connection:
            event_row = connection.execute(
                f"""
                SELECT COUNT(*) AS events, COUNT(DISTINCT session_id) AS sessions,
                       MIN(COALESCE(event.timestamp, session.started_at)) AS first_at,
                       MAX(COALESCE(event.timestamp, session.ended_at)) AS last_at
                FROM events event
                JOIN sessions session ON session.id=event.session_id
                WHERE {clauses}
                """,
                parameters,
            ).fetchone()
            text_row = connection.execute(
                f"""
                SELECT COUNT(*) AS text_units
                FROM text_units unit
                JOIN events event ON event.id=unit.event_id
                JOIN sessions session ON session.id=event.session_id
                WHERE {clauses}
                """,
                parameters,
            ).fetchone()
            raw_row = connection.execute(
                f"""
                SELECT COUNT(DISTINCT raw.id) AS raw_records,
                       COALESCE(SUM(raw.byte_length), 0) AS raw_bytes
                FROM raw_records raw
                JOIN events event ON event.raw_record_id=raw.id
                JOIN sessions session ON session.id=event.session_id
                WHERE {clauses}
                """,
                parameters,
            ).fetchone()
            total_events = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        events = int(event_row["events"] if event_row else 0)
        return ScopeEstimate(
            available=True,
            start=scope.start,
            end=scope.end,
            providers=providers,
            events=events,
            sessions=int(event_row["sessions"] if event_row else 0),
            text_units=int(text_row["text_units"] if text_row else 0),
            raw_records=int(raw_row["raw_records"] if raw_row else 0),
            raw_bytes=int(raw_row["raw_bytes"] if raw_row else 0),
            included_percent=(events / total_events * 100.0) if total_events else 0.0,
        )

    @staticmethod
    def _health(connection: Any) -> DatabaseHealth:
        schema_row = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        status_rows = connection.execute(
            """
            SELECT revision.status, COUNT(*) AS count
            FROM sources source
            JOIN source_revisions revision ON revision.id=source.active_revision_id
            GROUP BY revision.status
            """
        ).fetchall()
        statuses = {str(row["status"]): int(row["count"]) for row in status_rows}
        return DatabaseHealth(
            available=True,
            schema_version=int(schema_row["value"]) if schema_row else None,
            ingestion_complete=statuses.get("complete", 0),
            ingestion_in_progress=sum(statuses.get(key, 0) for key in ("pending", "ingesting", "partial")),
            ingestion_failed=statuses.get("failed", 0),
        )

    @staticmethod
    def _corpus(connection: Any) -> CorpusStats:
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in _COUNT_TABLES
        }
        database_size = int(connection.execute("SELECT pg_database_size(current_database())").fetchone()[0])
        storage: dict[str, int] = {}
        for table in _STORAGE_TABLES:
            storage[table] = int(
                connection.execute(f"SELECT pg_total_relation_size('{table}'::regclass)").fetchone()[0]
            )
        date_row = connection.execute(
            "SELECT MIN(timestamp) AS first_at, MAX(timestamp) AS last_at FROM events"
        ).fetchone()
        source_bytes = int(
            connection.execute(
                """
                SELECT COALESCE(SUM(revision.size_bytes), 0)
                FROM sources source JOIN source_revisions revision
                  ON revision.id=source.active_revision_id
                """
            ).fetchone()[0]
        )
        indexed_bytes = int(
            connection.execute(
                """
                SELECT COALESCE(SUM(revision.ingested_offset), 0)
                FROM sources source JOIN source_revisions revision
                  ON revision.id=source.active_revision_id
                """
            ).fetchone()[0]
        )
        parse_errors = int(
            connection.execute("SELECT COUNT(*) FROM events WHERE parse_error IS NOT NULL").fetchone()[0]
        )
        provider_rows = connection.execute(
            "SELECT provider, COUNT(*) AS count FROM sessions GROUP BY provider"
        ).fetchall()
        status_rows = connection.execute(
            """
            SELECT revision.status, COUNT(*) AS count
            FROM sources source JOIN source_revisions revision
              ON revision.id=source.active_revision_id
            GROUP BY revision.status
            """
        ).fetchall()
        return CorpusStats(
            database_size_bytes=database_size,
            table_storage_bytes=storage,
            **counts,
            parse_errors=parse_errors,
            source_bytes=source_bytes,
            indexed_bytes=indexed_bytes,
            first_event_at=_datetime_value(date_row["first_at"] if date_row else None),
            last_event_at=_datetime_value(date_row["last_at"] if date_row else None),
            providers={str(row["provider"]): int(row["count"]) for row in provider_rows},
            source_status={str(row["status"]): int(row["count"]) for row in status_rows},
        )

    @staticmethod
    def _reasoning(connection: Any, *, scan_raw_reasoning: bool) -> ReasoningFootprint:
        marker_clause = " OR ".join(
            f"encode(payload.payload, 'escape') LIKE '%{marker.replace('%', '%%')}%'"
            for marker in _REASONING_MARKERS
        )
        encrypted_clause = " OR ".join(
            f"encode(payload.payload, 'escape') LIKE '%{marker.replace('%', '%%')}%'"
            for marker in _ENCRYPTED_MARKERS
        )
        raw_row = None
        if scan_raw_reasoning:
            raw_row = connection.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE {marker_clause}) AS raw_reasoning_records,
                    COALESCE(SUM(raw.byte_length) FILTER (WHERE {marker_clause}), 0)
                        AS raw_reasoning_bytes,
                    COUNT(*) FILTER (WHERE {encrypted_clause}) AS encrypted_reasoning_records,
                    COALESCE(SUM(raw.byte_length) FILTER (WHERE {encrypted_clause}), 0)
                        AS encrypted_reasoning_bytes
                FROM raw_records raw
                JOIN raw_payloads payload ON payload.payload_hash=raw.payload_hash
                """
            ).fetchone()
        readable_row = connection.execute(
            """
            SELECT COUNT(*) AS units,
                   COALESCE(SUM(octet_length(content.text)), 0) AS bytes
            FROM text_units unit
            JOIN contents content ON content.id=unit.content_id
            WHERE unit.kind ILIKE '%reason%'
               OR unit.kind ILIKE '%thinking%'
            """
        ).fetchone()
        opaque_row = connection.execute(
            """
            SELECT COUNT(*) AS artifacts,
                   COALESCE(SUM(octet_length(value)), 0) AS bytes
            FROM artifacts
            WHERE kind IN ('opaque-payload', 'opaque_encoded_payload')
            """
        ).fetchone()
        semantic_row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE content.text ILIKE '%[reasoning]%') AS reasoning
            FROM semantic_windows semantic_window
            JOIN contents content ON content.id=semantic_window.content_id
            """
        ).fetchone()
        return ReasoningFootprint(
            raw_reasoning_records=(int(raw_row["raw_reasoning_records"]) if raw_row is not None else None),
            raw_reasoning_bytes=(int(raw_row["raw_reasoning_bytes"]) if raw_row is not None else None),
            encrypted_reasoning_records=(
                int(raw_row["encrypted_reasoning_records"]) if raw_row is not None else None
            ),
            encrypted_reasoning_bytes=(
                int(raw_row["encrypted_reasoning_bytes"]) if raw_row is not None else None
            ),
            readable_reasoning_units=int(readable_row["units"] if readable_row else 0),
            readable_reasoning_bytes=int(readable_row["bytes"] if readable_row else 0),
            opaque_artifact_count=int(opaque_row["artifacts"] if opaque_row else 0),
            opaque_artifact_bytes=int(opaque_row["bytes"] if opaque_row else 0),
            semantic_windows_total=int(semantic_row["total"] if semantic_row else 0),
            semantic_reasoning_windows=int(semantic_row["reasoning"] if semantic_row else 0),
            raw_scan_complete=scan_raw_reasoning,
        )

    @staticmethod
    def _machines(connection: Any) -> tuple[MachineNode, ...]:
        rows = connection.execute(
            """
            WITH source_counts AS (
                SELECT machine_id, COUNT(*) AS source_count
                FROM sources GROUP BY machine_id
            ), session_counts AS (
                SELECT machine_id, COUNT(*) AS session_count
                FROM sessions GROUP BY machine_id
            ), event_counts AS (
                SELECT session.machine_id, COUNT(*) AS event_count
                FROM events event
                JOIN sessions session ON session.id=event.session_id
                GROUP BY session.machine_id
            )
            SELECT machine.id, machine.name, machine.first_seen_at, machine.last_seen_at,
                   COALESCE(source_counts.source_count, 0) AS source_count,
                   COALESCE(session_counts.session_count, 0) AS session_count,
                   COALESCE(event_counts.event_count, 0) AS event_count
            FROM machines machine
            LEFT JOIN source_counts ON source_counts.machine_id=machine.id
            LEFT JOIN session_counts ON session_counts.machine_id=machine.id
            LEFT JOIN event_counts ON event_counts.machine_id=machine.id
            ORDER BY machine.name, machine.id
            """
        ).fetchall()
        return tuple(
            MachineNode(
                machine_id=str(row["id"]),
                name=str(row["name"]),
                first_seen_at=_datetime_value(row["first_seen_at"]),
                last_seen_at=_datetime_value(row["last_seen_at"]),
                source_count=int(row["source_count"]),
                session_count=int(row["session_count"]),
                event_count=int(row["event_count"]),
            )
            for row in rows
        )

    @staticmethod
    def _semantic_runs(connection: Any) -> tuple[SemanticRunStatus, ...]:
        rows = connection.execute(
            """
            SELECT run_key, profile, status, is_active, expected_count, chunk_count,
                   started_at, completed_at, error
            FROM semantic_runs
            ORDER BY started_at DESC, id DESC
            LIMIT 20
            """
        ).fetchall()
        return tuple(
            SemanticRunStatus(
                run_key=str(row["run_key"]),
                profile=str(row["profile"]),
                status=str(row["status"]),
                is_active=bool(row["is_active"]),
                expected_count=int(row["expected_count"]),
                chunk_count=int(row["chunk_count"]),
                started_at=_datetime_value(row["started_at"]),
                completed_at=_datetime_value(row["completed_at"]),
                error=_safe_error_text(row["error"]),
            )
            for row in rows
        )


def _event_scope_clause(scope: HistoryScope, providers: tuple[str, ...]) -> tuple[str, list[Any]]:
    clauses = ["COALESCE(event.timestamp, session.started_at) IS NOT NULL"]
    parameters: list[Any] = []
    if providers:
        placeholders = ", ".join("?" for _ in providers)
        clauses.append(f"session.provider IN ({placeholders})")
        parameters.extend(providers)
    if scope.start:
        clauses.append("COALESCE(event.timestamp, session.started_at) >= ?")
        parameters.append(datetime.combine(scope.start, time.min, tzinfo=UTC))
    if scope.end:
        clauses.append("COALESCE(event.timestamp, session.started_at) < ?")
        parameters.append(datetime.combine(scope.end + timedelta(days=1), time.min, tzinfo=UTC))
    return " AND ".join(clauses), parameters


def _loopback_host(value: str) -> bool:
    """Return whether a database bind/host is local-only."""

    if value in {"localhost", "local-socket", "::1"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _inspect_root(provider: str, root_value: Any, history_value: Any) -> ProviderRootStatus:
    if root_value is None:
        return ProviderRootStatus(
            provider=provider,
            path=None,
            history_file=None,
            exists=False,
            is_directory=False,
            readable=False,
            history_exists=None,
            history_bytes=None,
            issue="not configured",
        )
    root = Path(root_value).expanduser()
    history = Path(history_value).expanduser() if history_value is not None else None
    try:
        exists = root.exists()
        is_directory = root.is_dir() if exists else False
        readable = exists and is_directory and _readable(root)
        issue = None
        if not exists:
            issue = "missing"
        elif not is_directory:
            issue = "not a directory"
        elif not readable:
            issue = "not readable"
        history_exists: bool | None = None
        history_bytes: int | None = None
        if history is not None:
            history_exists = history.is_file()
            if history_exists:
                history_bytes = history.stat().st_size
        return ProviderRootStatus(
            provider=provider,
            path=str(root),
            history_file=str(history) if history is not None else None,
            exists=exists,
            is_directory=is_directory,
            readable=readable,
            history_exists=history_exists,
            history_bytes=history_bytes,
            issue=issue,
        )
    except OSError as exc:
        return ProviderRootStatus(
            provider=provider,
            path=str(root),
            history_file=str(history) if history is not None else None,
            exists=False,
            is_directory=False,
            readable=False,
            history_exists=False if history is not None else None,
            history_bytes=None,
            issue=type(exc).__name__,
        )


def _readable(path: Path) -> bool:
    """Check directory readability without opening or modifying source files."""

    try:
        next(path.iterdir(), None)
    except (OSError, PermissionError):
        return False
    return True


def _coerce_date(value: date | datetime | str | None, label: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"history {label} must be an ISO date (YYYY-MM-DD)") from exc
    raise TypeError(f"history {label} must be a date, datetime, ISO date, or None")


def _datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_error(error: BaseException) -> str:
    """Return an error class only; never serialize a DSN or server response."""

    return type(error).__name__


def _safe_error_text(value: Any) -> str | None:
    # A derived worker may include an input excerpt in its exception.  Setup
    # responses intentionally expose only whether an error was recorded.
    return "run error recorded" if value is not None else None
