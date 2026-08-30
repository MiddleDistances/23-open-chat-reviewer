"""Safe, guided installation of a source-only writer machine.

The public interface is ``install_writer``.  It hides config validation, private-file
placement, preflight inventory, resumable first sync, and operating-system scheduler
installation behind one deliberate command.  Permanent database credentials are read
from a generated private file and are never accepted as command-line arguments.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

_EXPORT = re.compile(r"^export (CHATREVIEW_[A-Z0-9_]+)=(.*)$")
_REQUIRED = (
    "CHATREVIEW_DATABASE_URL",
    "CHATREVIEW_MACHINE_ID",
    "CHATREVIEW_MACHINE_NAME",
    "CHATREVIEW_NODE_ROLE",
)


class WriterInstallError(RuntimeError):
    """A safe, user-correctable writer installation failure."""


@dataclass(frozen=True, slots=True)
class WriterInstallPlan:
    """Everything the installer needs to perform one guided writer setup."""

    config_path: Path
    data_dir: Path = Path(".chatreview")
    run_sync: bool = True
    install_schedule: bool = True
    history_since: date | None = None
    history_until: date | None = None

    def __post_init__(self) -> None:
        if (
            self.history_since is not None
            and self.history_until is not None
            and self.history_since > self.history_until
        ):
            raise WriterInstallError("history start must be on or before history end")


@dataclass(frozen=True, slots=True)
class WriterInstallResult:
    """Credential-free facts suitable for terminal confirmation and tests."""

    machine_name: str
    config_path: Path
    synced: bool
    schedule: str | None


def install_writer(plan: WriterInstallPlan) -> WriterInstallResult:
    """Install, verify, sync, and optionally schedule one writer.

    Existing identical configuration is reusable after an interrupted first run.
    A different existing configuration is never overwritten implicitly.
    """

    repo_root = Path(__file__).resolve().parents[2]
    source = plan.config_path.expanduser().resolve()
    if not source.is_file():
        raise WriterInstallError(f"writer configuration was not found: {source}")
    values = _read_writer_environment(source)

    system = platform.system()
    schedule_script: Path | None = None
    schedule_name: str | None = None
    if plan.install_schedule:
        if system == "Linux":
            schedule_script = repo_root / "scripts/install-systemd-writer.sh"
            schedule_name = "systemd user timer every three hours"
        elif system == "Darwin":
            if shutil.which("flock") is None:
                raise WriterInstallError("flock is required on macOS; run `brew install flock` and retry")
            schedule_script = repo_root / "scripts/install-launchd-writer.sh"
            schedule_name = "macOS LaunchAgent every three hours"
        else:
            raise WriterInstallError(
                f"automatic writer scheduling is not supported on {system}; retry with --no-schedule"
            )

    data_dir = plan.data_dir.expanduser().resolve()
    target = data_dir / "archive.env"
    data_dir.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.resolve() != source:
        if target.read_bytes() != source.read_bytes():
            raise WriterInstallError(f"refusing to overwrite a different writer configuration: {target}")
    elif target.resolve() != source:
        shutil.copyfile(source, target)
    target.chmod(0o600)

    cli = repo_root / ".venv/bin/open-chat-reviewer"
    sync_script = repo_root / "scripts/chatreview-sync.sh"
    if not cli.is_file() or not sync_script.is_file():
        raise WriterInstallError("run `uv sync` from the Open Chat Reviewer repository first")

    environment = dict(os.environ)
    environment.update(values)
    environment["CHATREVIEW_ENV_FILE"] = str(target)
    environment["CHATREVIEW_DATA_DIR"] = str(data_dir)

    _run(
        [str(cli), "db", "doctor", "--data-dir", str(data_dir)],
        repo_root=repo_root,
        environment=environment,
        step="database connection check",
    )
    _run(
        [str(cli), "inventory", "--data-dir", str(data_dir), "--no-git"],
        repo_root=repo_root,
        environment=environment,
        step="local source preview",
    )

    if plan.run_sync:
        sync_command = [str(sync_script)]
        if plan.history_since:
            sync_command.extend(("--history-since", plan.history_since.isoformat()))
        if plan.history_until:
            sync_command.extend(("--history-until", plan.history_until.isoformat()))
        _run(
            sync_command,
            repo_root=repo_root,
            environment=environment,
            step="first resumable sync",
        )

    if schedule_script is not None:
        _run(
            [str(schedule_script)],
            repo_root=repo_root,
            environment=environment,
            step="automatic sync installation",
        )

    return WriterInstallResult(
        machine_name=values["CHATREVIEW_MACHINE_NAME"],
        config_path=target,
        synced=plan.run_sync,
        schedule=schedule_name,
    )


def _read_writer_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXPORT.fullmatch(line)
        if match is None:
            raise WriterInstallError(f"unsupported content in writer configuration at line {line_number}")
        key, encoded = match.groups()
        try:
            parts = shlex.split(encoded, posix=True)
        except ValueError as exc:
            raise WriterInstallError(f"invalid writer configuration value at line {line_number}") from exc
        if len(parts) != 1:
            raise WriterInstallError(f"invalid writer configuration value at line {line_number}")
        values[key] = os.path.expandvars(parts[0])

    missing = [key for key in _REQUIRED if not values.get(key)]
    if missing:
        raise WriterInstallError("writer configuration is missing: " + ", ".join(missing))
    if values["CHATREVIEW_NODE_ROLE"] != "writer":
        raise WriterInstallError("configuration must contain CHATREVIEW_NODE_ROLE=writer")
    try:
        UUID(values["CHATREVIEW_MACHINE_ID"])
    except ValueError as exc:
        raise WriterInstallError("writer configuration contains an invalid machine ID") from exc
    if not values["CHATREVIEW_DATABASE_URL"].startswith(("postgresql://", "postgresql+")):
        raise WriterInstallError("writer configuration must contain a PostgreSQL database URL")
    return values


def _run(
    command: list[str],
    *,
    repo_root: Path,
    environment: Mapping[str, str],
    step: str,
) -> None:
    try:
        subprocess.run(command, cwd=repo_root, env=dict(environment), check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise WriterInstallError(f"{step} failed; fix the reported problem and rerun") from exc
