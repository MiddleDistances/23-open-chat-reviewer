"""Safely enable a central archive for Tailscale writer connections."""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit, urlunsplit

from chatreview.network import TailscaleIdentity


class CentralNetworkError(RuntimeError):
    """A safe, user-correctable central network preparation failure."""


@dataclass(frozen=True, slots=True)
class CentralNetworkResult:
    """Credential-free connection facts safe to print or expose in setup UI."""

    database_endpoint: str
    tailscale_name: str
    config_path: Path


CommandRunner = Callable[[list[str], Path, Mapping[str, str]], None]


def prepare_central_network(
    config_path: Path,
    identity: TailscaleIdentity,
    *,
    command_runner: CommandRunner | None = None,
) -> CentralNetworkResult:
    """Bind the bundled database to Tailscale while preserving private config.

    The database URL stays inside the mode-0600 environment file. Only the known
    network keys and URL host are changed; existing credentials and source settings
    are retained. Re-running the operation is safe.
    """

    path = config_path.expanduser().resolve()
    if not path.is_file():
        raise CentralNetworkError(f"central configuration was not found: {path}")
    original = path.read_text(encoding="utf-8")
    values = _environment_values(original)
    if values.get("CHATREVIEW_NODE_ROLE") != "central":
        raise CentralNetworkError("network preparation must run with a central-node configuration")
    database_url = values.get("CHATREVIEW_DATABASE_URL")
    if not database_url:
        raise CentralNetworkError("central configuration is missing CHATREVIEW_DATABASE_URL")
    repo_root = Path(__file__).resolve().parents[2]
    postgres_password = values.get("CHATREVIEW_POSTGRES_PASSWORD")
    if not postgres_password:
        postgres_password = _recover_bundled_password(repo_root)
    if not postgres_password:
        raise CentralNetworkError("automatic preparation requires the bundled PostgreSQL database")

    rewritten_url = _database_url_with_host(database_url, identity.ipv4)

    updates = {
        "CHATREVIEW_DATABASE_URL": rewritten_url,
        "CHATREVIEW_DB_BIND_ADDRESS": identity.ipv4,
        "CHATREVIEW_DB_PORT": values.get("CHATREVIEW_DB_PORT", "54329"),
        "CHATREVIEW_PUBLIC_DATABASE_HOST": identity.dns_name,
        "CHATREVIEW_WEB_TAILSCALE_ONLY": "1",
        "CHATREVIEW_POSTGRES_PASSWORD": postgres_password,
    }
    updated = _upsert_environment(original, updates)
    _write_private(path, updated)

    environment = dict(os.environ)
    environment.update(values)
    environment.update(updates)
    runner = command_runner or _run_command
    try:
        runner(["docker", "compose", "up", "-d", "--force-recreate", "db"], repo_root, environment)
    except (OSError, subprocess.CalledProcessError) as exc:
        _write_private(path, original)
        raise CentralNetworkError(
            "database reconfiguration failed; the private configuration was restored"
        ) from exc

    port = updates["CHATREVIEW_DB_PORT"]
    return CentralNetworkResult(
        database_endpoint=f"{identity.dns_name}:{port}",
        tailscale_name=identity.dns_name,
        config_path=path,
    )


def _environment_values(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith("export CHATREVIEW_") or "=" not in line:
            raise CentralNetworkError(f"unsupported central configuration at line {line_number}")
        key, encoded = line.removeprefix("export ").split("=", 1)
        try:
            decoded = shlex.split(encoded, posix=True)
        except ValueError as exc:
            raise CentralNetworkError(f"invalid central configuration at line {line_number}") from exc
        if len(decoded) != 1:
            raise CentralNetworkError(f"invalid central configuration at line {line_number}")
        values[key] = os.path.expandvars(decoded[0])
    return values


def _upsert_environment(content: str, updates: Mapping[str, str]) -> str:
    remaining = dict(updates)
    lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        key = None
        if stripped.startswith("export CHATREVIEW_") and "=" in stripped:
            key = stripped.removeprefix("export ").split("=", 1)[0]
        if key in remaining:
            lines.append(f"export {key}={shlex.quote(remaining.pop(key))}")
        else:
            lines.append(line)
    lines.extend(f"export {key}={shlex.quote(value)}" for key, value in remaining.items())
    return "\n".join(lines) + "\n"


def _database_url_with_host(database_url: str, host: str) -> str:
    try:
        parsed = urlsplit(database_url)
        if not parsed.scheme.startswith("postgresql") or not parsed.hostname:
            raise ValueError
        userinfo, separator, _address = parsed.netloc.rpartition("@")
        prefix = f"{userinfo}@" if separator else ""
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError as exc:
        raise CentralNetworkError("central configuration contains an invalid database URL") from exc
    return urlunsplit(parsed._replace(netloc=f"{prefix}{host}{port}"))


def _write_private(path: Path, content: str) -> None:
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _recover_bundled_password(repo_root: Path) -> str | None:
    """Recover a legacy bundled password without exposing it in command output."""

    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "printenv", "POSTGRES_PASSWORD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    password = result.stdout.strip()
    return password or None


def _run_command(command: list[str], cwd: Path, environment: Mapping[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=dict(environment), check=True)
