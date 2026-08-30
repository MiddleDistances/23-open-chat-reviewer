"""Machine-local summary-agent selection and background refresh jobs.

The browser may select only fixed provider identifiers. It never supplies an
executable, argument list, credential, or prompt. CLI providers reuse the local
account through :mod:`chatreview.summary_providers`; the archive still sends only
the bounded evidence packet produced by the resume-surface module.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from chatreview.resume import ProviderResumeModel, ResumeSurfaceRefresher
from chatreview.summary_providers import (
    SummaryProvider,
    cli_provider_statuses,
    provider_from_environment,
)

SummaryAgentId = Literal["qwen", "codex-cli", "claude-cli", "gemini-cli"]
ACTIVE_SUMMARY_STATES = frozenset({"queued", "running"})
SELECTION_FILE = "summary-agent.json"
STATE_FILE = "summary-run.json"


class SummaryJobError(RuntimeError):
    """Base error safe to report through the summary-agent API."""


class SummaryJobAlreadyRunning(SummaryJobError):
    """Raised when this machine already owns a live summary refresh."""


@dataclass(frozen=True, slots=True)
class SummaryRunPlan:
    """Validated, bounded inputs accepted from the setup page."""

    provider: SummaryAgentId
    days: int = 30
    limit: int = 40
    per_project_limit: int = 3

    def __post_init__(self) -> None:
        if self.provider not in {"qwen", "codex-cli", "claude-cli", "gemini-cli"}:
            raise ValueError("unknown summary agent")
        if not 1 <= self.days <= 365:
            raise ValueError("summary history must be between 1 and 365 days")
        if not 1 <= self.limit <= 100:
            raise ValueError("summary batch size must be between 1 and 100")
        if not 1 <= self.per_project_limit <= 10:
            raise ValueError("per-project limit must be between 1 and 10")

    @property
    def provider_kind(self) -> str:
        return "openai-compatible" if self.provider == "qwen" else self.provider


ProviderFactory = Callable[[SummaryRunPlan], SummaryProvider]


class SummaryRunManager:
    """Own one background summary refresh and persist credential-free progress."""

    def __init__(
        self,
        settings: Any,
        *,
        provider_factory: ProviderFactory | None = None,
        state_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_path = state_path or self.data_dir / STATE_FILE
        self.provider_factory = provider_factory or self._provider_from_plan
        self._mutex = threading.RLock()
        self._thread: threading.Thread | None = None

    def start(self, plan: SummaryRunPlan) -> dict[str, Any]:
        """Persist the selection, queue a bounded refresh, and return immediately."""

        with self._mutex:
            current = self.status()
            if current["active"]:
                raise SummaryJobAlreadyRunning("a summary refresh is already running")
            save_summary_agent(self.data_dir, plan.provider)
            now = _now()
            state = {
                "job_id": uuid.uuid4().hex,
                "status": "queued",
                "provider": plan.provider,
                "days": plan.days,
                "limit": plan.limit,
                "per_project_limit": plan.per_project_limit,
                "message": "Summary refresh queued",
                "started_at": now,
                "updated_at": now,
                "finished_at": None,
                "error": None,
                "result": None,
                "owner_pid": os.getpid(),
            }
            self._write(state)
            self._thread = threading.Thread(
                target=self._run,
                args=(plan,),
                name=f"chatreview-summary-{state['job_id'][:8]}",
                daemon=True,
            )
            self._thread.start()
            return _public_state(state)

    def status(self) -> dict[str, Any]:
        """Return the durable state and mark a dead web-process job interrupted."""

        with self._mutex:
            state = self._read()
            if state is None:
                return _public_state({"status": "idle"})
            if state.get("status") in ACTIVE_SUMMARY_STATES:
                owner_pid = _integer(state.get("owner_pid"))
                if owner_pid and owner_pid != os.getpid() and not _pid_alive(owner_pid):
                    state["status"] = "interrupted"
                    state["message"] = "The web process stopped before the summary batch finished"
                    state["finished_at"] = _now()
                    state["updated_at"] = state["finished_at"]
                    state["owner_pid"] = None
                    self._write(state)
            return _public_state(state)

    def wait(self, timeout: float | None = None) -> dict[str, Any]:
        """Wait for the in-process job; primarily useful for deployment checks and tests."""

        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.status()

    def _provider_from_plan(self, plan: SummaryRunPlan) -> SummaryProvider:
        return provider_from_environment(
            provider=plan.provider_kind,
            runtime_root=self.data_dir / "cli-runs",
        )

    def _run(self, plan: SummaryRunPlan) -> None:
        provider: SummaryProvider | None = None
        state = self._read() or {"status": "running"}
        try:
            state["status"] = "running"
            state["message"] = "Selecting recent work threads"
            state["updated_at"] = _now()
            self._write(state)
            provider = self.provider_factory(plan)

            def progress(message: str) -> None:
                state["message"] = _safe_message(message)
                state["updated_at"] = _now()
                self._write(state)

            summary = ResumeSurfaceRefresher(
                self.settings.database_url,
                ProviderResumeModel(provider),
                progress=progress,
            ).run(
                days=plan.days,
                limit=plan.limit,
                per_project_limit=plan.per_project_limit,
            )
            state["status"] = "complete" if summary.status == "complete" else summary.status
            state["result"] = asdict(summary)
            state["message"] = (
                f"{summary.generated} summaries generated; {summary.reused} unchanged; "
                f"{summary.failed} failed"
            )
            if state["status"] not in {"complete", "partial"}:
                state["error"] = "The summary refresh did not complete"
        except BaseException as exc:
            state["status"] = "failed"
            state["error"] = _safe_message(exc)
            state["message"] = "Summary refresh failed"
        finally:
            if provider is not None:
                with suppress(Exception):
                    provider.close()
            state["finished_at"] = _now()
            state["updated_at"] = state["finished_at"]
            state["owner_pid"] = None
            self._write(state)

    def _read(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True))
        with suppress(OSError):
            temporary.chmod(0o600)
        temporary.replace(self.state_path)


def summary_agent_catalog() -> list[dict[str, Any]]:
    """Return fixed GUI choices without returning executable paths or credentials."""

    model = os.environ.get("CHATREVIEW_SUMMARY_MODEL", "").strip()
    base_url = os.environ.get("CHATREVIEW_SUMMARY_BASE_URL", "").strip()
    qwen_configured = bool(model and base_url)
    return [
        {
            "id": "qwen",
            "label": "Local Qwen",
            "installed": qwen_configured,
            "authenticated": None,
            "detail": (
                f"Configured local model: {model}"
                if qwen_configured
                else "Set CHATREVIEW_SUMMARY_MODEL and CHATREVIEW_SUMMARY_BASE_URL first"
            ),
        },
        *cli_provider_statuses(),
    ]


def save_summary_agent(data_dir: Path, provider: SummaryAgentId) -> None:
    """Persist only an allowlisted provider id; CLI credentials remain CLI-owned."""

    if provider not in {"qwen", "codex-cli", "claude-cli", "gemini-cli"}:
        raise ValueError("unknown summary agent")
    path = Path(data_dir) / SELECTION_FILE
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"provider": provider, "updated_at": _now()}, indent=2, sort_keys=True)
    )
    with suppress(OSError):
        temporary.chmod(0o600)
    temporary.replace(path)


def load_summary_agent(data_dir: Path) -> SummaryAgentId | None:
    """Read the credential-free local selection, if one has been saved."""

    path = Path(data_dir) / SELECTION_FILE
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    provider = payload.get("provider") if isinstance(payload, dict) else None
    if provider in {"qwen", "codex-cli", "claude-cli", "gemini-cli"}:
        return provider
    return None


def selected_provider_kind(data_dir: Path) -> str | None:
    """Translate the saved GUI choice into the provider-factory identifier."""

    selected = load_summary_agent(data_dir)
    if selected == "qwen":
        return "openai-compatible"
    return selected


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in state.items() if key != "owner_pid"}
    status = str(result.get("status") or "idle")
    result["status"] = status
    result["active"] = status in ACTIVE_SUMMARY_STATES
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_message(value: object) -> str:
    return " ".join(str(value).split())[:1_000]


def _integer(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
