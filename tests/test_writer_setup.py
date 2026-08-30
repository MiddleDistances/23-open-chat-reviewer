from __future__ import annotations

import stat
import subprocess
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from chatreview import cli
from chatreview.writer_setup import (
    WriterInstallError,
    WriterInstallPlan,
    install_writer,
)


def _config(path: Path, *, role: str = "writer", name: str = "my-laptop") -> Path:
    path.write_text(
        "\n".join(
            (
                "export CHATREVIEW_DATABASE_URL='postgresql://writer:secret@archive.ts.net:54329/chatreview'",
                "export CHATREVIEW_MACHINE_ID='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'",
                f"export CHATREVIEW_MACHINE_NAME='{name}'",
                f"export CHATREVIEW_NODE_ROLE='{role}'",
                'export CHATREVIEW_CODEX_ROOT="$HOME/.codex"',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_install_writer_places_private_config_and_runs_guided_steps(tmp_path: Path, monkeypatch) -> None:
    source = _config(tmp_path / "laptop.env")
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("chatreview.writer_setup.platform.system", lambda: "Linux")
    monkeypatch.setattr("chatreview.writer_setup.subprocess.run", fake_run)

    result = install_writer(
        WriterInstallPlan(
            config_path=source,
            data_dir=tmp_path / "runtime",
            history_since=date(2026, 1, 1),
            history_until=date(2026, 8, 30),
        )
    )

    target = tmp_path / "runtime/archive.env"
    assert result.machine_name == "my-laptop"
    assert result.synced is True
    assert result.schedule == "systemd user timer every three hours"
    assert target.read_bytes() == source.read_bytes()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [command[1:3] for command in commands[:2]] == [
        ["db", "doctor"],
        ["inventory", "--data-dir"],
    ]
    assert commands[2][-4:] == [
        "--history-since",
        "2026-01-01",
        "--history-until",
        "2026-08-30",
    ]
    assert commands[3][0].endswith("scripts/install-systemd-writer.sh")


def test_install_writer_refuses_non_writer_or_different_existing_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("chatreview.writer_setup.platform.system", lambda: "Linux")
    with pytest.raises(WriterInstallError, match="NODE_ROLE=writer"):
        install_writer(
            WriterInstallPlan(
                config_path=_config(tmp_path / "central.env", role="central"),
                data_dir=tmp_path / "runtime",
            )
        )

    source = _config(tmp_path / "writer.env")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "archive.env").write_text("different", encoding="utf-8")
    with pytest.raises(WriterInstallError, match="refusing to overwrite"):
        install_writer(WriterInstallPlan(config_path=source, data_dir=runtime))


def test_writer_install_cli_never_echoes_database_credentials(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path / "writer.env")
    observed: list[WriterInstallPlan] = []

    def fake_install(plan: WriterInstallPlan):
        observed.append(plan)
        from chatreview.writer_setup import WriterInstallResult

        return WriterInstallResult(
            machine_name="my-laptop",
            config_path=tmp_path / ".chatreview/archive.env",
            synced=False,
            schedule=None,
        )

    monkeypatch.setattr(cli, "install_writer", fake_install)
    result = CliRunner().invoke(
        cli.app,
        ["writer", "install", str(config), "--no-sync", "--no-schedule"],
    )

    assert result.exit_code == 0, result.output
    assert observed[0].run_sync is False
    assert "my-laptop" in result.output
    assert "secret" not in result.output
    assert "postgresql" not in result.output
