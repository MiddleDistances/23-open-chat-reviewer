from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

from chatreview import central_network
from chatreview.central_network import CentralNetworkError, prepare_central_network
from chatreview.network import TailscaleIdentity


def _central_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "export CHATREVIEW_DATABASE_URL=postgresql://chatreview:private-password@127.0.0.1:54329/chatreview",
                "export CHATREVIEW_POSTGRES_PASSWORD=private-password",
                "export CHATREVIEW_NODE_ROLE=central",
                "export CHATREVIEW_MACHINE_NAME=central-host",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def test_prepare_central_network_updates_only_private_config_and_recreates_database(
    tmp_path: Path,
) -> None:
    config = tmp_path / ".chatreview/archive.env"
    _central_config(config)
    calls: list[tuple[list[str], dict[str, str]]] = []

    def run(command: list[str], _cwd: Path, environment: dict[str, str]) -> None:
        calls.append((command, environment))

    result = prepare_central_network(
        config,
        TailscaleIdentity(ipv4="100.101.102.103", dns_name="central.example.ts.net"),
        command_runner=run,
    )

    content = config.read_text(encoding="utf-8")
    assert "CHATREVIEW_DB_BIND_ADDRESS=100.101.102.103" in content
    assert "CHATREVIEW_PUBLIC_DATABASE_HOST=central.example.ts.net" in content
    assert "@100.101.102.103:54329/chatreview" in content
    assert "private-password" in content
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert result.database_endpoint == "central.example.ts.net:54329"
    assert calls[0][0] == ["docker", "compose", "up", "-d", "--force-recreate", "db"]
    assert "private-password" not in " ".join(calls[0][0])


def test_prepare_central_network_restores_config_when_database_reconfigure_fails(
    tmp_path: Path,
) -> None:
    config = tmp_path / ".chatreview/archive.env"
    _central_config(config)
    original = config.read_text(encoding="utf-8")

    def fail(_command: list[str], _cwd: Path, _environment: dict[str, str]) -> None:
        raise subprocess.CalledProcessError(1, ["docker", "compose"])

    with pytest.raises(CentralNetworkError, match="configuration was restored"):
        prepare_central_network(
            config,
            TailscaleIdentity(ipv4="100.101.102.103", dns_name="central.example.ts.net"),
            command_runner=fail,
        )

    assert config.read_text(encoding="utf-8") == original


def test_prepare_central_network_refuses_writer_config(tmp_path: Path) -> None:
    config = tmp_path / "writer.env"
    _central_config(config)
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "CHATREVIEW_NODE_ROLE=central", "CHATREVIEW_NODE_ROLE=writer"
        ),
        encoding="utf-8",
    )

    with pytest.raises(CentralNetworkError, match="central-node"):
        prepare_central_network(
            config,
            TailscaleIdentity(ipv4="100.101.102.103", dns_name="central.example.ts.net"),
        )


def test_prepare_central_network_recovers_legacy_bundled_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / ".chatreview/archive.env"
    _central_config(config)
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "export CHATREVIEW_POSTGRES_PASSWORD=private-password\n", ""
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        central_network.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "recovered-password\n", ""),
    )

    prepare_central_network(
        config,
        TailscaleIdentity(ipv4="100.101.102.103", dns_name="central.example.ts.net"),
        command_runner=lambda *_args: None,
    )

    content = config.read_text(encoding="utf-8")
    assert "CHATREVIEW_POSTGRES_PASSWORD=recovered-password" in content
