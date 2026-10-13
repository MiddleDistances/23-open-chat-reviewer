from __future__ import annotations

import json
import stat
from pathlib import Path

from typer.testing import CliRunner

from chatreview import cli

runner = CliRunner()


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.request = None

    def open(self, request, *, timeout: float):
        self.request = request
        return self.response


def test_summary_configure_auto_selects_one_model_without_database(
    tmp_path: Path, monkeypatch
) -> None:
    opener = _Opener(_Response(b'{"data":[{"id":"qwen3.8-27b"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )

    result = runner.invoke(
        cli.app,
        [
            "summary",
            "configure",
            "--data-dir",
            str(tmp_path),
            "--base-url",
            "http://127.0.0.1:18000/v1/",
            "--disable-thinking",
        ],
    )

    assert result.exit_code == 0, result.output
    runtime = tmp_path / "summary-provider.json"
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o600
    assert json.loads(runtime.read_text(encoding="utf-8"))["model"] == "qwen3.8-27b"
    assert "postgres" not in result.output.lower()
    assert "qwen3.8-27b" in result.output


def test_summary_configure_requires_model_when_endpoint_advertises_many(
    tmp_path: Path, monkeypatch
) -> None:
    opener = _Opener(_Response(b'{"data":[{"id":"one"},{"id":"two"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )

    result = runner.invoke(
        cli.app,
        [
            "summary",
            "configure",
            "--data-dir",
            str(tmp_path),
            "--base-url",
            "http://127.0.0.1:8000/v1",
        ],
    )

    assert result.exit_code != 0
    assert "--model" in result.output
    assert not (tmp_path / "summary-provider.json").exists()


def test_summary_probe_does_not_write_configuration(tmp_path: Path, monkeypatch) -> None:
    opener = _Opener(_Response(b'{"data":[{"id":"one"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )

    result = runner.invoke(
        cli.app,
        [
            "summary",
            "probe",
            "--data-dir",
            str(tmp_path),
            "--base-url",
            "http://127.0.0.1:8000/v1",
            "--model",
            "one",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "ready" in result.output.lower()
    assert not (tmp_path / "summary-provider.json").exists()


def test_summary_use_persists_only_allowlisted_provider(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["summary", "use", "codex-cli", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "summary-agent.json").read_text()) ["provider"] == "codex-cli"


def test_summary_use_rejects_arbitrary_provider(tmp_path: Path) -> None:
    result = runner.invoke(
        cli.app,
        ["summary", "use", "--data-dir", str(tmp_path), "arbitrary"],
    )

    assert result.exit_code != 0
    assert not (tmp_path / "summary-agent.json").exists()


def test_summary_commands_default_to_configured_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CHATREVIEW_DATA_DIR", str(tmp_path))

    result = runner.invoke(cli.app, ["summary", "use", "codex-cli"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "summary-agent.json").is_file()
