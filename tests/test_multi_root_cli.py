from __future__ import annotations

import json
import shlex
from pathlib import Path
from uuid import UUID

import pytest
from typer.testing import CliRunner

import chatreview.cli as cli
from chatreview.cli import app
from chatreview.ingest import IngestSummary
from chatreview.source_roots import save_source_roots

MACHINE_ID = UUID("11111111-2222-3333-4444-555555555555")
ROOT_ENV_KEYS = (
    "CHATREVIEW_CODEX_ROOT",
    "CHATREVIEW_CODEX_ROOTS",
    "CHATREVIEW_CLAUDE_ROOT",
    "CHATREVIEW_CLAUDE_ROOTS",
    "CHATREVIEW_GEMINI_ROOT",
    "CHATREVIEW_GEMINI_ROOTS",
    "CHATREVIEW_OPENCODE_ROOT",
    "CHATREVIEW_OPENCODE_ROOTS",
    "CHATREVIEW_GIT_ROOT",
    "CHATREVIEW_GIT_ROOTS",
)


def _prepare_environment(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Make CLI tests independent of the developer machine's source folders."""

    for key in (
        "CHATREVIEW_DATA_DIR",
        "CHATREVIEW_DATABASE_URL",
        "CHATREVIEW_MACHINE_ID",
        "CHATREVIEW_MACHINE_NAME",
        "CHATREVIEW_CONTRIBUTOR",
        *ROOT_ENV_KEYS,
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", "postgresql:///chatreview-cli-test")
    monkeypatch.setenv("CHATREVIEW_MACHINE_ID", str(MACHINE_ID))
    for provider in ("codex", "claude", "gemini", "opencode", "git"):
        monkeypatch.setenv(f"CHATREVIEW_{provider.upper()}_ROOTS", "[]")


def test_sync_repeated_codex_roots_reach_sync_in_order_and_are_deduplicated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_environment(monkeypatch, tmp_path / "home")
    first = tmp_path / "first codex archive"
    second = tmp_path / "second codex archive"
    observed: dict[str, object] = {}

    def fake_sync(settings, **kwargs):
        observed["settings"] = settings
        observed["kwargs"] = kwargs
        return IngestSummary()

    monkeypatch.setattr(cli, "sync_sources", fake_sync)
    result = CliRunner().invoke(
        app,
        [
            "sync",
            "--data-dir",
            str(tmp_path / ".chatreview"),
            "--provider",
            "codex",
            "--codex-root",
            str(first),
            "--codex-root",
            str(second),
            "--codex-root",
            str(first),
            "--no-git",
        ],
    )

    assert result.exit_code == 0, result.output
    settings = observed["settings"]
    assert settings.codex_roots == (first.resolve(), second.resolve())
    assert observed["kwargs"]["providers"] == {"codex"}


def test_sources_check_succeeds_when_only_second_repeated_root_has_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_environment(monkeypatch, tmp_path / "home")
    first = tmp_path / "first codex archive"
    second = tmp_path / "second codex archive"
    (second / "sessions").mkdir(parents=True)

    result = CliRunner().invoke(
        app,
        [
            "sources",
            "check",
            "--data-dir",
            str(tmp_path / ".chatreview"),
            "--codex-root",
            str(first),
            "--codex-root",
            str(second),
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"INFO] codex: {first.resolve()}" in result.output
    assert f"OK  ] codex: {second.resolve()}" in result.output


@pytest.mark.parametrize("disabled", [False, True])
def test_sources_check_fails_for_empty_or_disabled_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, disabled: bool
) -> None:
    _prepare_environment(monkeypatch, tmp_path / "home")
    args = [
        "sources",
        "check",
        "--data-dir",
        str(tmp_path / ".chatreview"),
    ]
    if disabled:
        # The provider lists are already explicitly empty in the test environment.
        pass
    else:
        args.extend(["--codex-root", str(tmp_path / "empty codex archive")])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 1, result.output
    assert "No Codex, Claude, Gemini, OpenCode, or Git sources found" in result.output
    if disabled:
        assert "no folders are configured" in result.output
    else:
        assert "configured folders contain no sources" in result.output


def test_sources_check_honors_machine_local_runtime_root_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_environment(monkeypatch, tmp_path / "home")
    data_dir = tmp_path / ".chatreview"
    first = tmp_path / "runtime first codex archive"
    second = tmp_path / "runtime second codex archive"
    (second / "sessions").mkdir(parents=True)
    save_source_roots(
        data_dir,
        {"codex": [str(first), str(second)], "claude": [], "gemini": [], "git": []},
    )

    result = CliRunner().invoke(app, ["sources", "check", "--data-dir", str(data_dir)])

    assert result.exit_code == 0, result.output
    assert f"INFO] codex: {first.resolve()}" in result.output
    assert f"OK  ] codex: {second.resolve()}" in result.output


def test_init_emits_plural_json_root_variables_without_legacy_singular_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_environment(monkeypatch, tmp_path / "home")
    output = tmp_path / "archive.env"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--output",
            str(output),
            "--role",
            "writer",
            "--database-url",
            "postgresql://chatreview@central/chatreview",
        ],
    )

    assert result.exit_code == 0, result.output
    content = output.read_text(encoding="utf-8")
    for provider in ("CODEX", "CLAUDE", "GEMINI", "OPENCODE", "GIT"):
        plural_key = f"CHATREVIEW_{provider}_ROOTS"
        singular_key = f"CHATREVIEW_{provider}_ROOT"
        assert f"{plural_key}=" in content
        assert f"{singular_key}=" not in content
        line = next(line for line in content.splitlines() if line.startswith(f"export {plural_key}="))
        assignment = shlex.split(line.removeprefix("export "), posix=True)[0]
        key, separator, value = assignment.partition("=")
        assert key == plural_key
        assert separator == "="
        assert isinstance(json.loads(value), list)
