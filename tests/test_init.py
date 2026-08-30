from __future__ import annotations

import stat
from pathlib import Path

from typer.testing import CliRunner

from chatreview import cli

runner = CliRunner()


def _read_exports(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, value = line.removeprefix("export ").split("=", 1)
        values[key] = value.strip("'")
    return values


def test_init_prefers_tailscale_for_central_node(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "archive.env"
    monkeypatch.setattr(
        cli,
        "_tailscale_identity",
        lambda: ("100.101.102.103", "archive.example.ts.net"),
    )

    result = runner.invoke(cli.app, ["init", "--output", str(output)])

    assert result.exit_code == 0, result.output
    values = _read_exports(output)
    assert values["CHATREVIEW_NODE_ROLE"] == "central"
    assert values["CHATREVIEW_DB_BIND_ADDRESS"] == "100.101.102.103"
    assert values["CHATREVIEW_PUBLIC_DATABASE_HOST"] == "archive.example.ts.net"
    assert values["CHATREVIEW_WEB_TAILSCALE_ONLY"] == "1"
    assert values["CHATREVIEW_POSTGRES_PASSWORD"] != "chatreview"
    assert values["CHATREVIEW_POSTGRES_PASSWORD"] in values["CHATREVIEW_DATABASE_URL"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_init_can_force_loopback(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "archive.env"
    monkeypatch.setattr(
        cli,
        "_tailscale_identity",
        lambda: ("100.101.102.103", "archive.example.ts.net"),
    )

    result = runner.invoke(
        cli.app,
        ["init", "--output", str(output), "--network", "loopback"],
    )

    assert result.exit_code == 0, result.output
    values = _read_exports(output)
    assert values["CHATREVIEW_DB_BIND_ADDRESS"] == "127.0.0.1"
    assert values["CHATREVIEW_WEB_TAILSCALE_ONLY"] == "0"


def test_writer_init_requires_central_database_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHATREVIEW_DATABASE_URL", raising=False)

    result = runner.invoke(
        cli.app,
        ["init", "--output", str(tmp_path / "archive.env"), "--role", "writer"],
    )

    assert result.exit_code == 2
    assert "writer nodes require" in result.output


def test_writer_init_uses_environment_url_without_central_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    output = tmp_path / "archive.env"
    database_url = "postgresql://writer:secret@archive.example.ts.net:54329/chatreview"
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", database_url)

    result = runner.invoke(
        cli.app,
        ["init", "--output", str(output), "--role", "writer"],
    )

    assert result.exit_code == 0, result.output
    values = _read_exports(output)
    assert values["CHATREVIEW_NODE_ROLE"] == "writer"
    assert values["CHATREVIEW_DATABASE_URL"] == database_url
    assert "CHATREVIEW_POSTGRES_PASSWORD" not in values
    assert "CHATREVIEW_DB_BIND_ADDRESS" not in values
