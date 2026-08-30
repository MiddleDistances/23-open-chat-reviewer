from __future__ import annotations

import io
import json
import threading
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from chatreview.setup_jobs import (
    BuildAlreadyRunning,
    SetupBuildManager,
    SetupBuildPlan,
    build_commands,
)


class FakeProcess:
    _next_pid = 41_000

    def __init__(self, output: str = "", *, block: bool = False) -> None:
        self.pid = self._next_pid
        type(self)._next_pid += 1
        self.stdout = io.StringIO(output)
        self.returncode: int | None = None
        self.terminated = False
        self._release = threading.Event()
        if not block:
            self._release.set()

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        if not self._release.wait(timeout):
            raise TimeoutError("fake process did not finish")
        if self.returncode is None:
            self.returncode = -15 if self.terminated else 0
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self._release.set()

    def kill(self) -> None:
        self.terminate()
        self.returncode = -9


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(data_dir=tmp_path / "runtime")


def test_plan_normalises_setup_page_payload_and_validates_dates() -> None:
    plan = SetupBuildPlan.from_mapping(
        {
            "providers": ["Claude", "codex", "claude"],
            "includeGitMetadata": False,
            "historyStart": "2026-01-02",
            "historyEnd": "2026-01-31",
            "preserveEncryptedReasoning": False,
            "includeReadableReasoningInSearch": True,
            "includeReasoningInProjection": True,
        }
    )

    assert plan.providers == ("claude", "codex")
    assert plan.include_git is False
    assert plan.history_scope == (date(2026, 1, 2), date(2026, 1, 31))
    assert plan.preserve_encrypted_reasoning is False
    assert plan.include_readable_reasoning_in_search is True
    assert plan.include_reasoning_in_projection is True

    with pytest.raises(ValueError, match="on or before"):
        SetupBuildPlan(history_since="2026-02-01", history_until="2026-01-01")
    with pytest.raises(ValueError, match="unsupported provider"):
        SetupBuildPlan(providers=("wat",))


def test_build_commands_are_local_argv_and_include_policy_flags(tmp_path: Path) -> None:
    plan = SetupBuildPlan(
        providers=("codex",),
        include_git=False,
        history_since="2026-01-02",
        history_until="2026-01-31",
        preserve_encrypted_reasoning=False,
        include_reasoning_in_projection=True,
    )

    commands = build_commands(plan, repository_root=tmp_path)

    assert [command.phase for command in commands] == ["sync", "refresh", "semantic"]
    assert commands[0].argv == (
        str(tmp_path / "scripts" / "chatreview-sync.sh"),
        "--no-git",
        "--provider",
        "codex",
        "--history-since",
        "2026-01-02",
        "--history-until",
        "2026-01-31",
    )
    assert commands[1].argv == (str(tmp_path / ".venv" / "bin" / "open-chat-reviewer"), "refresh")
    assert commands[2].argv == (
        str(tmp_path / ".venv" / "bin" / "open-chat-reviewer"),
        "semantic",
        "refresh",
        "--model",
        "Qwen/Qwen3-Embedding-0.6B",
        "--model-revision",
        "72bb2d1e482afe83dcebe9496edc693ad1967a0f",
        "--dimensions",
        "512",
        "--reasoning",
        "--no-context",
        "--provider",
        "codex",
        "--date-from",
        "2026-01-02",
        "--date-to",
        "2026-01-31",
    )
    assert all("postgres" not in argument for command in commands for argument in command.argv)


def test_manager_runs_phases_persists_safe_state_and_inherits_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", "postgresql://user:secret@example.test/db")
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        seen.append((argv, kwargs))
        return FakeProcess("progress line\n")

    manager = SetupBuildManager(
        _settings(tmp_path),
        repository_root=tmp_path,
        process_factory=factory,
    )
    started = manager.start(
        SetupBuildPlan(
            providers=("codex",),
            include_git=False,
            preserve_encrypted_reasoning=False,
            run_semantic_refresh=False,
        )
    )

    assert started.status == "queued"
    finished = manager.wait(timeout=2)
    assert finished.status == "complete"
    assert finished.completed == 2
    assert finished.active is False
    assert len(seen) == 2
    assert seen[0][1]["env"]["CHATREVIEW_DATABASE_URL"].endswith("/db")
    assert seen[0][1]["env"]["CHATREVIEW_RAW_REASONING_RETENTION"] == "redact"
    assert seen[0][1]["env"]["CHATREVIEW_RAW_REASONING_RETENTION_OVERRIDE"] == "redact"
    assert "shell" not in seen[0][1]

    state_path = tmp_path / "runtime" / "setup-build.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "complete"
    assert "secret" not in state_path.read_text(encoding="utf-8")
    log_path = Path(payload["log_file"])
    assert log_path.is_relative_to(tmp_path / "runtime")
    assert "secret" not in log_path.read_text(encoding="utf-8")


def test_manager_allows_only_one_job_and_cancel_is_safe(tmp_path: Path) -> None:
    process_ready = threading.Event()
    processes: list[FakeProcess] = []

    def factory(_argv: list[str], **_kwargs: Any) -> FakeProcess:
        process = FakeProcess(block=True)
        processes.append(process)
        process_ready.set()
        return process

    manager = SetupBuildManager(_settings(tmp_path), repository_root=tmp_path, process_factory=factory)
    manager.start(SetupBuildPlan(providers=("codex",), include_git=False, run_semantic_refresh=False))
    assert process_ready.wait(2)

    second = SetupBuildManager(_settings(tmp_path), repository_root=tmp_path, process_factory=factory)
    with pytest.raises(BuildAlreadyRunning):
        second.start(SetupBuildPlan(providers=("codex",), include_git=False, run_semantic_refresh=False))

    assert manager.cancel().status == "cancelling"
    assert manager.wait(timeout=2).status == "cancelled"
    assert processes[0].terminated is True


def test_status_marks_orphaned_running_state_interrupted(tmp_path: Path) -> None:
    manager = SetupBuildManager(_settings(tmp_path), repository_root=tmp_path)
    manager.data_dir.mkdir(parents=True)
    manager.state_path.write_text(
        json.dumps(
            {
                "job_id": "orphan",
                "status": "syncing",
                "phase": "sync",
                "message": "still running",
                "completed": 0,
                "total": 3,
                "percent": 0,
                "owner_pid": 999_999_991,
                "process_pid": 999_999_992,
                "plan": {},
                "commands": [],
            }
        ),
        encoding="utf-8",
    )

    status = manager.status()

    assert status.status == "interrupted"
    assert status.active is False
    assert status.error == "interrupted after process restart"
