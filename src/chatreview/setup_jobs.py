"""Durable, local setup builds launched from the setup page.

The setup planner is intentionally read-only.  This module is the small write
seam used after an operator accepts a planner preview: it turns a validated
plan into the repository's sync wrapper followed by deterministic refresh and,
optionally, semantic refresh commands.

There are two important boundaries here:

* source roots and the database URL are never copied into job state; the child
  process inherits the current environment and receives no shell string;
* the wrapper remains responsible for the authoritative sync lock.  The manager
  owns a second, machine-local lock so that two GUI requests cannot queue two
  derived refreshes behind one another.

``SetupBuildManager`` is deliberately independent of FastAPI.  A web adapter
can call :meth:`start`, :meth:`status`, and :meth:`cancel`, while tests inject a
small process factory and inspect the pure :func:`build_commands` result.
"""

from __future__ import annotations

import errno
import json
import os
import re
import signal
import subprocess
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO, cast

from chatreview.embedding_models import (
    DEFAULT_EMBEDDING_PRESET,
    EmbeddingModelError,
    embedding_preset,
)

ProviderName = Literal["codex", "claude", "gemini", "git"]
BuildPhase = Literal["sync", "refresh", "semantic"]
BuildState = Literal[
    "idle",
    "queued",
    "syncing",
    "refreshing",
    "embedding",
    "cancelling",
    "complete",
    "failed",
    "cancelled",
    "interrupted",
]

CONVERSATION_PROVIDERS = ("codex", "claude", "gemini")
ALL_PROVIDERS = (*CONVERSATION_PROVIDERS, "git")
DEFAULT_STATE_NAME = "setup-build.json"
DEFAULT_LOCK_NAME = "setup-build.lock"
DEFAULT_LOG_DIRECTORY = "logs"

# These flags are part of the CLI contract owned by the parent integration.
# Keeping them in one place makes a future CLI spelling change auditable.
SEMANTIC_REASONING_OPTION = "--reasoning"
SEMANTIC_NO_REASONING_OPTION = "--no-reasoning"
SEMANTIC_DATE_FROM_OPTION = "--date-from"
SEMANTIC_DATE_TO_OPTION = "--date-to"

_ACTIVE_STATES = frozenset({"queued", "syncing", "refreshing", "embedding", "cancelling"})
_DATE_FORMAT = "%Y-%m-%d"
_MAX_MESSAGE_CHARS = 1_000
_SECRET_ENV_KEYS = frozenset(
    {
        "CHATREVIEW_DATABASE_URL",
        "DATABASE_URL",
        "PGPASSWORD",
        "CHATREVIEW_MCP_BEARER_TOKEN",
        "MCP_BEARER_TOKEN",
    }
)
_URL_SECRET_PATTERN = re.compile(
    r"(?P<scheme>(?:postgres(?:ql)?|mysql|redis)://)(?P<credentials>[^/@\s]+):(?P<password>[^/@\s]+)@"
)


class BuildJobError(RuntimeError):
    """Base class for setup-build failures safe to expose to the UI."""


class BuildAlreadyRunning(BuildJobError):
    """Raised when another setup build owns the local job lock."""


class InvalidBuildPlan(BuildJobError, ValueError):
    """Raised when a setup payload is not safe to turn into CLI arguments."""


class ProcessLike(Protocol):
    """Minimal subprocess contract required by the manager."""

    pid: int
    stdout: TextIO | None
    returncode: int | None

    def poll(self) -> int | None:
        """Return the exit code if the child has exited."""

    def wait(self, timeout: float | None = None) -> int:
        """Wait for the child and return its exit code."""

    def terminate(self) -> None:
        """Ask the child to stop."""

    def kill(self) -> None:
        """Force the child to stop."""


ProcessFactory = Callable[..., ProcessLike]
Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class SetupBuildPlan:
    """Validated choices for one local archive build.

    Dates are inclusive UTC calendar days.  ``providers`` refers to the
    conversation adapters; Git is an independent metadata choice represented by
    ``include_git`` so a form cannot accidentally turn off Git by changing its
    conversation-provider checkboxes.
    """

    providers: tuple[str, ...] = CONVERSATION_PROVIDERS
    include_git: bool = True
    history_since: date | str | None = None
    history_until: date | str | None = None
    preserve_encrypted_reasoning: bool = True
    include_readable_reasoning_in_search: bool = False
    include_reasoning_in_projection: bool = False
    embedding_preset: str = DEFAULT_EMBEDDING_PRESET
    run_semantic_refresh: bool = True

    def __post_init__(self) -> None:
        raw_providers: Sequence[str] = (
            (self.providers,) if isinstance(self.providers, str) else self.providers
        )
        normalised = tuple(
            dict.fromkeys(
                str(value).strip().lower() for value in raw_providers if str(value).strip()
            )
        )
        if not normalised:
            raise InvalidBuildPlan("at least one conversation provider must be selected")
        unsupported = tuple(value for value in normalised if value not in ALL_PROVIDERS)
        if unsupported:
            raise InvalidBuildPlan(f"unsupported provider: {', '.join(unsupported)}")
        # Git is represented separately in the GUI.  Accept it in an API payload
        # for compatibility, but normalise it to include_git rather than emit a
        # duplicate --provider git argument.
        include_git = bool(self.include_git or "git" in normalised)
        conversation = tuple(value for value in normalised if value != "git")
        if not conversation:
            raise InvalidBuildPlan("at least one conversation provider must be selected")
        object.__setattr__(self, "providers", conversation)
        object.__setattr__(self, "include_git", include_git)
        object.__setattr__(self, "history_since", _coerce_date(self.history_since, "history_since"))
        object.__setattr__(self, "history_until", _coerce_date(self.history_until, "history_until"))
        if self.history_since and self.history_until and self.history_since > self.history_until:
            raise InvalidBuildPlan("history_since must be on or before history_until")
        object.__setattr__(self, "preserve_encrypted_reasoning", bool(self.preserve_encrypted_reasoning))
        object.__setattr__(
            self,
            "include_readable_reasoning_in_search",
            bool(self.include_readable_reasoning_in_search),
        )
        object.__setattr__(
            self,
            "include_reasoning_in_projection",
            bool(self.include_reasoning_in_projection),
        )
        try:
            embedding_preset(self.embedding_preset)
        except EmbeddingModelError as exc:
            raise InvalidBuildPlan(str(exc)) from exc
        object.__setattr__(self, "run_semantic_refresh", bool(self.run_semantic_refresh))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> SetupBuildPlan:
        """Parse snake_case or setup-page camelCase values without leaking extras."""

        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise InvalidBuildPlan("build plan must be an object")
        providers = value.get("providers", CONVERSATION_PROVIDERS)
        include_git = value.get("include_git", value.get("includeGitMetadata", True))
        history_since = value.get("history_since", value.get("historyStart"))
        history_until = value.get("history_until", value.get("historyEnd"))
        preserve = value.get(
            "preserve_encrypted_reasoning",
            value.get("preserveEncryptedReasoning", True),
        )
        include_reasoning = value.get(
            "include_reasoning_in_projection",
            value.get("includeReasoningInProjection", False),
        )
        include_search_reasoning = value.get(
            "include_readable_reasoning_in_search",
            value.get("includeReadableReasoningInSearch", False),
        )
        run_semantic = value.get(
            "run_semantic_refresh",
            value.get("runSemanticRefresh", value.get("includeSemantic", True)),
        )
        selected_embedding = value.get(
            "embedding_preset",
            value.get("embeddingPreset", DEFAULT_EMBEDDING_PRESET),
        )
        return cls(
            providers=tuple(providers) if not isinstance(providers, str) else (providers,),
            include_git=bool(include_git),
            history_since=history_since or None,
            history_until=history_until or None,
            preserve_encrypted_reasoning=bool(preserve),
            include_readable_reasoning_in_search=bool(include_search_reasoning),
            include_reasoning_in_projection=bool(include_reasoning),
            embedding_preset=str(selected_embedding),
            run_semantic_refresh=bool(run_semantic),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return only JSON-safe, non-secret plan fields."""

        return {
            "providers": list(self.providers),
            "include_git": self.include_git,
            "history_since": self.history_since.isoformat() if self.history_since else None,
            "history_until": self.history_until.isoformat() if self.history_until else None,
            "preserve_encrypted_reasoning": self.preserve_encrypted_reasoning,
            "include_readable_reasoning_in_search": self.include_readable_reasoning_in_search,
            "include_reasoning_in_projection": self.include_reasoning_in_projection,
            "embedding_preset": self.embedding_preset,
            "run_semantic_refresh": self.run_semantic_refresh,
        }

    @property
    def history_scope(self) -> tuple[date | None, date | None]:
        """Return the inclusive date pair used by sync and semantic phases."""

        return self.history_since, self.history_until


# Short aliases are useful to adapters that call this a build rather than a setup
# job.  The canonical name remains explicit in API schemas and documentation.
BuildPlan = SetupBuildPlan


@dataclass(frozen=True, slots=True)
class BuildCommand:
    """One phase command and the safe metadata displayed in job status."""

    phase: BuildPhase
    argv: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "argv": list(self.argv)}


def build_commands(
    plan: SetupBuildPlan | Mapping[str, Any] | None = None,
    *,
    repository_root: Path | str | None = None,
    cli_path: Path | str | None = None,
    sync_wrapper: Path | str | None = None,
) -> tuple[BuildCommand, ...]:
    """Construct the exact argv sequence for a plan without running it.

    The sync wrapper is the authority for its own lock and preflight.  Refresh
    and semantic phases use the same repository-local CLI directly, keeping all
    commands independent of the user's shell, aliases, and current PATH.
    """

    selected = plan if isinstance(plan, SetupBuildPlan) else SetupBuildPlan.from_mapping(plan)
    root = _repository_root(repository_root)
    cli = Path(cli_path) if cli_path is not None else root / ".venv" / "bin" / "open-chat-reviewer"
    wrapper = Path(sync_wrapper) if sync_wrapper is not None else root / "scripts" / "chatreview-sync.sh"
    sync_argv: list[str] = [str(wrapper), "--git" if selected.include_git else "--no-git"]
    for provider in selected.providers:
        sync_argv.extend(("--provider", provider))
    if selected.include_git:
        sync_argv.extend(("--provider", "git"))
    if selected.history_since:
        sync_argv.extend(("--history-since", selected.history_since.strftime(_DATE_FORMAT)))
    if selected.history_until:
        sync_argv.extend(("--history-until", selected.history_until.strftime(_DATE_FORMAT)))
    commands = [BuildCommand("sync", tuple(sync_argv))]
    commands.append(BuildCommand("refresh", (str(cli), "refresh")))
    if selected.run_semantic_refresh:
        model = embedding_preset(selected.embedding_preset)
        semantic_argv = [
            str(cli),
            "semantic",
            "refresh",
            "--model",
            model.model_name,
            "--model-revision",
            model.revision,
            "--dimensions",
            str(model.dimensions),
        ]
        semantic_argv.append(
            SEMANTIC_REASONING_OPTION
            if selected.include_reasoning_in_projection
            else SEMANTIC_NO_REASONING_OPTION
        )
        semantic_argv.append("--no-context")
        for provider in selected.providers:
            semantic_argv.extend(("--provider", provider))
        if selected.history_since:
            semantic_argv.extend((SEMANTIC_DATE_FROM_OPTION, selected.history_since.strftime(_DATE_FORMAT)))
        if selected.history_until:
            semantic_argv.extend((SEMANTIC_DATE_TO_OPTION, selected.history_until.strftime(_DATE_FORMAT)))
        commands.append(BuildCommand("semantic", tuple(semantic_argv)))
    return tuple(commands)


@dataclass(frozen=True, slots=True)
class BuildStatus:
    """Public, content-free snapshot of the current or last build."""

    job_id: str | None = None
    status: BuildState = "idle"
    phase: BuildPhase | None = None
    message: str | None = None
    completed: int = 0
    total: int = 0
    percent: float = 0.0
    started_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    exit_code: int | None = None
    log_file: str | None = None
    plan: dict[str, Any] = field(default_factory=dict)
    commands: tuple[BuildCommand, ...] = ()
    owner_pid: int | None = None
    process_pid: int | None = None

    @property
    def active(self) -> bool:
        """Whether the status represents a build that may still be running."""

        return self.status in _ACTIVE_STATES

    def to_dict(self) -> dict[str, Any]:
        """Serialize status for API polling, omitting no secret-bearing fields."""

        return {
            "job_id": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "completed": self.completed,
            "total": self.total,
            "percent": self.percent,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "exit_code": self.exit_code,
            "log_file": self.log_file,
            "plan": dict(self.plan),
            "commands": [command.to_dict() for command in self.commands],
            "active": self.active,
        }


@dataclass(slots=True)
class _JobContext:
    plan: SetupBuildPlan
    commands: tuple[BuildCommand, ...]
    job_id: str
    log_path: Path
    cancel_requested: threading.Event = field(default_factory=threading.Event)


class SetupBuildManager:
    """Own one durable setup build for a machine-local web process."""

    def __init__(
        self,
        settings: Any,
        *,
        repository_root: Path | str | None = None,
        process_factory: ProcessFactory | None = None,
        clock: Clock | None = None,
        state_path: Path | str | None = None,
        lock_path: Path | str | None = None,
    ) -> None:
        self.settings = settings
        self.data_dir = _data_directory(settings)
        self.repository_root = _repository_root(repository_root)
        self.process_factory = process_factory or _default_process_factory
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state_path = _data_path(self.data_dir, state_path, DEFAULT_STATE_NAME)
        self.lock_path = _data_path(self.data_dir, lock_path, DEFAULT_LOCK_NAME)
        self._thread: threading.Thread | None = None
        self._process: ProcessLike | None = None
        self._context: _JobContext | None = None
        self._file_lock: _FileLock | None = None
        self._mutex = threading.RLock()

    def start(self, plan: SetupBuildPlan | Mapping[str, Any] | None = None) -> BuildStatus:
        """Queue a build and return immediately with its durable status."""

        selected = plan if isinstance(plan, SetupBuildPlan) else SetupBuildPlan.from_mapping(plan)
        with self._mutex:
            self._recover_stale_state()
            existing = self._read_status()
            if existing.active:
                raise BuildAlreadyRunning("an Open Chat Reviewer setup build is already running")
            lock = _FileLock(self.lock_path)
            if not lock.acquire():
                raise BuildAlreadyRunning("another Open Chat Reviewer setup build owns the local lock")
            self._file_lock = lock
            job_id = uuid.uuid4().hex
            commands = build_commands(selected, repository_root=self.repository_root)
            log_path = self.data_dir / DEFAULT_LOG_DIRECTORY / f"setup-build-{job_id}.log"
            context = _JobContext(selected, commands, job_id, log_path)
            self._context = context
            state = self._new_state(context)
            self._write_state(state)
            self._thread = threading.Thread(
                target=self._run,
                args=(context,),
                name=f"chatreview-setup-{job_id[:8]}",
                daemon=True,
            )
            self._thread.start()
            return _status_from_state(state)

    def status(self) -> BuildStatus:
        """Read the durable status and recover orphaned active state if needed."""

        with self._mutex:
            self._recover_stale_state()
            return self._read_status()

    def cancel(self) -> BuildStatus:
        """Request safe process-group cancellation and return current status."""

        with self._mutex:
            state = self._read_raw_state()
            if not state or str(state.get("status")) not in _ACTIVE_STATES:
                return _status_from_state(state) if state else BuildStatus()
            state["status"] = "cancelling"
            state["message"] = "Stop requested; waiting for the current command to exit"
            state["updated_at"] = self._now()
            self._write_state(state)
            context = self._context
            if context is not None:
                context.cancel_requested.set()
            # The context is held by the worker; the process reference is guarded
            # by the manager mutex.  A new web request can still stop a child that
            # was started by this manager instance.
            process = self._process
            if process is not None:
                _terminate_process_group(process)
            else:
                process_pid = _int_or_none(state.get("process_pid"))
                if process_pid:
                    _terminate_pid(process_pid)
            return _status_from_state(state)

    def wait(self, timeout: float | None = None) -> BuildStatus:
        """Wait for this manager's worker in tests or a graceful web shutdown."""

        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.status()

    def _run(self, context: _JobContext) -> None:
        try:
            state = self._read_raw_state() or self._new_state(context)
            for index, command in enumerate(context.commands):
                if context.cancel_requested.is_set():
                    self._finish_cancelled(state)
                    return
                state = self._phase_state(state, context, command, index)
                self._write_state(state)
                exit_code = self._run_command(context, command, state)
                if context.cancel_requested.is_set():
                    self._finish_cancelled(state, exit_code)
                    return
                if exit_code != 0:
                    self._finish_failed(state, exit_code)
                    return
                state["completed"] = index + 1
                state["percent"] = 100.0 if index + 1 == len(context.commands) else round(
                    (index + 1) * 100.0 / len(context.commands), 1
                )
                state["message"] = f"{command.phase.capitalize()} phase complete"
                state["updated_at"] = self._now()
                self._write_state(state)
            state["status"] = "complete"
            state["phase"] = None
            state["message"] = "Archive build complete"
            state["finished_at"] = self._now()
            state["updated_at"] = state["finished_at"]
            state["owner_pid"] = None
            state["process_pid"] = None
            self._write_state(state)
        except BaseException as exc:
            # Never persist a traceback or the database URL.  The log has the
            # sanitized error, while the state remains safe for API responses.
            state = self._read_raw_state() or self._new_state(context)
            self._finish_failed(state, None, _safe_message(exc))
        finally:
            self._process = None
            self._context = None
            lock = self._file_lock
            self._file_lock = None
            if lock is not None:
                lock.release()

    def _run_command(self, context: _JobContext, command: BuildCommand, state: dict[str, Any]) -> int:
        environment = os.environ.copy()
        # The sync wrapper loads archive.env itself, so this explicit child
        # override is what makes the GUI plan authoritative for this run.  The
        # environment is intentionally never persisted in state or logs.
        environment["CHATREVIEW_RAW_REASONING_RETENTION"] = (
            "preserve" if context.plan.preserve_encrypted_reasoning else "redact"
        )
        environment["CHATREVIEW_RAW_REASONING_RETENTION_OVERRIDE"] = environment[
            "CHATREVIEW_RAW_REASONING_RETENTION"
        ]
        self._append_log(context, f"starting {command.phase}: {_display_argv(command.argv)}")
        try:
            process = self.process_factory(
                list(command.argv),
                cwd=str(self.repository_root),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except BaseException as exc:
            message = _safe_message(exc)
            self._append_log(context, f"failed to start {command.phase}: {message}")
            state["message"] = message
            state["updated_at"] = self._now()
            self._write_state(state)
            return 127
        self._process = process
        state["process_pid"] = _safe_pid(process)
        state["updated_at"] = self._now()
        self._write_state(state)
        stream = process.stdout
        if stream is not None:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                message = _safe_message(line)
                self._append_log(context, message)
                state["message"] = message
                state["updated_at"] = self._now()
                self._write_state(state)
        try:
            exit_code = int(process.wait())
        except BaseException as exc:
            self._append_log(context, f"{command.phase} wait failed: {_safe_message(exc)}")
            exit_code = 1
        self._process = None
        state["process_pid"] = None
        state["exit_code"] = exit_code
        state["updated_at"] = self._now()
        self._write_state(state)
        self._append_log(context, f"finished {command.phase}: exit_status={exit_code}")
        return exit_code

    def _phase_state(
        self,
        state: dict[str, Any],
        context: _JobContext,
        command: BuildCommand,
        index: int,
    ) -> dict[str, Any]:
        status: BuildState = {
            "sync": "syncing",
            "refresh": "refreshing",
            "semantic": "embedding",
        }[command.phase]
        state["status"] = status
        state["phase"] = command.phase
        state["completed"] = index
        state["total"] = len(context.commands)
        state["percent"] = round(index * 100.0 / len(context.commands), 1)
        state["message"] = f"{command.phase.capitalize()} phase running"
        state["updated_at"] = self._now()
        return state

    def _new_state(self, context: _JobContext) -> dict[str, Any]:
        now = self._now()
        return {
            "job_id": context.job_id,
            "status": "queued",
            "phase": None,
            "message": "Build queued",
            "completed": 0,
            "total": len(context.commands),
            "percent": 0.0,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
            "error": None,
            "exit_code": None,
            "log_file": str(context.log_path),
            "plan": context.plan.to_dict(),
            "commands": [command.to_dict() for command in context.commands],
            "owner_pid": os.getpid(),
            "process_pid": None,
        }

    def _finish_failed(
        self,
        state: dict[str, Any],
        exit_code: int | None,
        message: str | None = None,
    ) -> None:
        now = self._now()
        state["status"] = "failed"
        state["phase"] = state.get("phase")
        state["message"] = message or "Build command failed"
        state["error"] = message or "Build command failed"
        state["exit_code"] = exit_code
        state["finished_at"] = now
        state["updated_at"] = now
        state["owner_pid"] = None
        state["process_pid"] = None
        self._write_state(state)

    def _finish_cancelled(self, state: dict[str, Any], exit_code: int | None = None) -> None:
        now = self._now()
        state["status"] = "cancelled"
        state["message"] = "Build cancelled by the operator"
        state["error"] = "cancelled by operator"
        state["exit_code"] = exit_code
        state["finished_at"] = now
        state["updated_at"] = now
        state["owner_pid"] = None
        state["process_pid"] = None
        self._write_state(state)

    def _recover_stale_state(self) -> None:
        state = self._read_raw_state()
        if not state or str(state.get("status")) not in _ACTIVE_STATES:
            return
        if _lock_is_held(self.lock_path):
            return
        process_pid = _int_or_none(state.get("process_pid"))
        if process_pid and process_pid != os.getpid() and _pid_alive(process_pid):
            _terminate_pid(process_pid)
        now = self._now()
        state["status"] = "interrupted"
        state["phase"] = state.get("phase")
        state["message"] = "Build interrupted after the owning process stopped"
        state["error"] = "interrupted after process restart"
        state["finished_at"] = now
        state["updated_at"] = now
        state["owner_pid"] = None
        state["process_pid"] = None
        self._write_state(state)

    def _read_status(self) -> BuildStatus:
        state = self._read_raw_state()
        return _status_from_state(state) if state else BuildStatus()

    def _read_raw_state(self) -> dict[str, Any] | None:
        try:
            payload = self.state_path.read_text(encoding="utf-8")
            value = json.loads(payload)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return value if isinstance(value, dict) else None

    def _write_state(self, state: Mapping[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.tmp")
        encoded = json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        temporary.write_text(encoded, encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.state_path)

    def _append_log(self, context: _JobContext, message: str) -> None:
        context.log_path.parent.mkdir(parents=True, exist_ok=True)
        safe = _safe_message(message)
        with context.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{self._now()} {safe}\n")
        os.chmod(context.log_path, 0o600)

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class _FileLock:
    """Small advisory lock kept open for the lifetime of one build."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: TextIO | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (ImportError, BlockingIOError, OSError) as exc:
            if isinstance(exc, OSError) and exc.errno not in {errno.EACCES, errno.EAGAIN}:
                self.handle.close()
                self.handle = None
                raise
            if self.handle is not None:
                self.handle.close()
                self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        self.handle.close()
        self.handle = None


def _default_process_factory(argv: Sequence[str], **kwargs: Any) -> ProcessLike:
    """Spawn a child without shell interpretation."""

    return cast(ProcessLike, subprocess.Popen(list(argv), shell=False, **kwargs))


def _repository_root(value: Path | str | None) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "scripts" / "chatreview-sync.sh").exists():
        return source_root
    return Path.cwd().resolve()


def _data_directory(settings: Any) -> Path:
    value = getattr(settings, "data_dir", None)
    if value is None:
        raise InvalidBuildPlan("settings.data_dir is required for durable setup jobs")
    return Path(value).expanduser().resolve()


def _data_path(data_dir: Path, value: Path | str | None, default_name: str) -> Path:
    candidate = data_dir / default_name if value is None else Path(value).expanduser()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(data_dir)
    except ValueError as exc:
        raise InvalidBuildPlan("setup job state and locks must remain under settings.data_dir") from exc
    return resolved


def _coerce_date(value: date | str | None, label: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise InvalidBuildPlan(f"{label} must use YYYY-MM-DD") from exc
    raise InvalidBuildPlan(f"{label} must be a date or YYYY-MM-DD")


def _status_from_state(state: Mapping[str, Any] | None) -> BuildStatus:
    if not state:
        return BuildStatus()
    commands: list[BuildCommand] = []
    for item in state.get("commands", ()):
        if not isinstance(item, Mapping):
            continue
        phase = item.get("phase")
        argv = item.get("argv")
        if phase in {"sync", "refresh", "semantic"} and isinstance(argv, list | tuple):
            commands.append(BuildCommand(cast(BuildPhase, phase), tuple(str(value) for value in argv)))
    raw_status = str(state.get("status", "idle"))
    status = cast(BuildState, raw_status if raw_status in {
        "idle", "queued", "syncing", "refreshing", "embedding", "cancelling",
        "complete", "failed", "cancelled", "interrupted",
    } else "failed")
    plan_value = state.get("plan")
    plan = dict(plan_value) if isinstance(plan_value, Mapping) else {}
    return BuildStatus(
        job_id=str(state["job_id"]) if state.get("job_id") is not None else None,
        status=status,
        phase=cast(BuildPhase | None, state.get("phase")),
        message=_safe_message(state.get("message")) if state.get("message") else None,
        completed=_int_or_zero(state.get("completed")),
        total=_int_or_zero(state.get("total")),
        percent=float(state.get("percent", 0.0) or 0.0),
        started_at=str(state["started_at"]) if state.get("started_at") else None,
        updated_at=str(state["updated_at"]) if state.get("updated_at") else None,
        finished_at=str(state["finished_at"]) if state.get("finished_at") else None,
        error=_safe_message(state.get("error")) if state.get("error") else None,
        exit_code=_int_or_none(state.get("exit_code")),
        log_file=str(state["log_file"]) if state.get("log_file") else None,
        plan=plan,
        commands=tuple(commands),
        owner_pid=_int_or_none(state.get("owner_pid")),
        process_pid=_int_or_none(state.get("process_pid")),
    )


def _safe_message(value: Any) -> str:
    if isinstance(value, BaseException):
        value = f"{type(value).__name__}: {value}"
    text = str(value or "").replace("\x00", " ").replace("\r", " ").replace("\n", " ").strip()
    for key in _SECRET_ENV_KEYS:
        secret = os.environ.get(key)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = _URL_SECRET_PATTERN.sub(r"\g<scheme>[REDACTED]@", text)
    return text[:_MAX_MESSAGE_CHARS]


def _display_argv(argv: Sequence[str]) -> str:
    # argv contains only local paths and policy values.  Keep the display
    # shell-neutral and avoid inventing a string that could be re-executed.
    return " ".join(_safe_message(value) for value in argv)


def _safe_pid(process: ProcessLike) -> int | None:
    try:
        pid = int(process.pid)
    except (AttributeError, TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    return _int_or_none(value) or 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def _lock_is_held(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        import fcntl

        with path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return False
    except (ImportError, OSError):
        return False


def _terminate_process_group(process: ProcessLike) -> None:
    pid = _safe_pid(process)
    if pid and pid != os.getpid():
        with suppress(ProcessLookupError, PermissionError, OSError):
            os.killpg(pid, signal.SIGTERM)
    with suppress(AttributeError, OSError):
        process.terminate()


def _terminate_pid(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        return
    with suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(pid, signal.SIGTERM)
    if not _pid_alive(pid):
        return
    with suppress(ProcessLookupError, PermissionError, OSError):
        os.kill(pid, signal.SIGTERM)
