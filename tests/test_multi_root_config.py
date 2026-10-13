from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from chatreview.config import Settings, default_settings
from chatreview.source_roots import save_source_roots

MACHINE_ID = UUID("11111111-2222-3333-4444-555555555555")
ROOT_ENV_KEYS = (
    "CHATREVIEW_CODEX_ROOT",
    "CHATREVIEW_CODEX_ROOTS",
    "CHATREVIEW_CLAUDE_ROOT",
    "CHATREVIEW_CLAUDE_ROOTS",
    "CHATREVIEW_GEMINI_ROOT",
    "CHATREVIEW_GEMINI_ROOTS",
    "CHATREVIEW_GIT_ROOT",
    "CHATREVIEW_GIT_ROOTS",
)


def _prepare_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give each settings test the minimum complete environment."""

    for key in (
        "CHATREVIEW_DATA_DIR",
        "CHATREVIEW_DATABASE_URL",
        "CHATREVIEW_MACHINE_ID",
        "CHATREVIEW_MACHINE_NAME",
        "CHATREVIEW_CONTRIBUTOR",
        "CHATREVIEW_RAW_REASONING_RETENTION",
        *ROOT_ENV_KEYS,
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", "postgresql:///chatreview-config-test")
    monkeypatch.setenv("CHATREVIEW_MACHINE_ID", str(MACHINE_ID))


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
    environment: dict[str, str] | None = None,
    **kwargs: object,
) -> Settings:
    _prepare_environment(monkeypatch)
    for key, value in (environment or {}).items():
        monkeypatch.setenv(key, value)
    return default_settings(data_dir=data_dir, **kwargs)


@pytest.mark.parametrize(
    ("missing_key", "message"),
    [
        ("CHATREVIEW_DATABASE_URL", "CHATREVIEW_DATABASE_URL is required"),
        ("CHATREVIEW_MACHINE_ID", "CHATREVIEW_MACHINE_ID is required"),
    ],
)
def test_default_settings_requires_database_url_and_machine_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    missing_key: str,
    message: str,
) -> None:
    _prepare_environment(monkeypatch)
    monkeypatch.delenv(missing_key)

    with pytest.raises(ValueError, match=message):
        default_settings(data_dir=tmp_path / ".chatreview")


def test_legacy_singular_root_environment_is_a_single_root_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "legacy codex root"
    settings = _settings(
        monkeypatch,
        tmp_path / ".chatreview",
        environment={"CHATREVIEW_CODEX_ROOT": str(root)},
    )

    assert settings.codex_roots == (root.resolve(),)
    assert settings.codex_root == root.resolve()
    assert settings.roots_for("codex") == (root.resolve(),)


def test_plural_json_roots_preserve_spaces_and_colons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    roots = [tmp_path / "first archive: with spaces", tmp_path / "second archive: with spaces"]
    settings = _settings(
        monkeypatch,
        tmp_path / ".chatreview",
        environment={
            "CHATREVIEW_CODEX_ROOTS": json.dumps([str(root) for root in roots]),
            "CHATREVIEW_CODEX_ROOT": str(tmp_path / "singular-should-not-win"),
        },
    )

    assert settings.codex_roots == tuple(root.resolve() for root in roots)
    assert settings.roots_for("codex") == tuple(root.resolve() for root in roots)


def test_explicit_repeated_roots_take_precedence_over_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configured = [tmp_path / "configured-one", tmp_path / "configured-two"]
    settings = _settings(
        monkeypatch,
        tmp_path / ".chatreview",
        environment={
            "CHATREVIEW_CODEX_ROOTS": json.dumps([str(tmp_path / "environment-root")]),
            "CHATREVIEW_CODEX_ROOT": str(tmp_path / "legacy-root"),
        },
        codex_root=[configured[0], configured[1], configured[0]],
    )

    assert settings.codex_roots == tuple(root.resolve() for root in configured)


def test_runtime_source_roots_file_wins_over_plural_and_singular_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / ".chatreview"
    runtime_root = tmp_path / "runtime codex root"
    save_source_roots(data_dir, {"codex": [str(runtime_root)]})
    settings = _settings(
        monkeypatch,
        data_dir,
        environment={
            "CHATREVIEW_CODEX_ROOTS": json.dumps([str(tmp_path / "env-plural")]),
            "CHATREVIEW_CODEX_ROOT": str(tmp_path / "env-singular"),
        },
    )

    assert settings.codex_roots == (runtime_root.resolve(),)
    assert settings.roots_for("codex") == (runtime_root.resolve(),)


def test_explicit_empty_runtime_list_disables_provider_but_keeps_singular_alias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    data_dir = tmp_path / ".chatreview"
    save_source_roots(data_dir, {"codex": []})
    settings = _settings(
        monkeypatch,
        data_dir,
        environment={
            "CHATREVIEW_CODEX_ROOTS": json.dumps([str(tmp_path / "env-plural")]),
            "CHATREVIEW_CODEX_ROOT": str(tmp_path / "env-singular"),
        },
    )

    assert settings.codex_roots == ()
    assert settings.roots_for("codex") == ()
    assert isinstance(settings.codex_root, Path)
    assert settings.codex_history == settings.codex_root / "history.jsonl"


def test_duplicate_normalized_roots_are_removed_in_default_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "codex archive"
    aliases = [root, root / ".", root / ".." / root.name]
    settings = _settings(
        monkeypatch,
        tmp_path / ".chatreview",
        environment={"CHATREVIEW_CODEX_ROOTS": json.dumps([str(path) for path in aliases])},
    )

    assert settings.codex_roots == (root.resolve(),)


@pytest.mark.parametrize(
    ("raw_value", "message"),
    [
        ("not-json", "CHATREVIEW_CODEX_ROOTS must be a JSON array of paths"),
        (json.dumps({"path": "/tmp/not-a-list"}), "CHATREVIEW_CODEX_ROOTS:.*list of paths"),
        (json.dumps([42]), "CHATREVIEW_CODEX_ROOTS:.*must be a string"),
    ],
)
def test_plural_root_environment_reports_invalid_json_and_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    raw_value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(
            monkeypatch,
            tmp_path / ".chatreview",
            environment={"CHATREVIEW_CODEX_ROOTS": raw_value},
        )


def test_legacy_manually_constructed_settings_still_support_roots_for(tmp_path: Path) -> None:
    codex = tmp_path / "codex"
    claude = tmp_path / "claude"
    gemini = tmp_path / "gemini"
    git = tmp_path / "git"
    settings = Settings(
        database_url="postgresql:///chatreview",
        machine_id=MACHINE_ID,
        machine_name="legacy-test",
        contributor=None,
        data_dir=tmp_path / ".chatreview",
        codex_root=codex,
        codex_history=codex / "history.jsonl",
        claude_root=claude,
        claude_history=claude / "history.jsonl",
        gemini_root=gemini,
        git_root=git,
    )

    assert settings.roots_for("codex") == (codex,)
    assert settings.roots_for("claude") == (claude,)
    assert settings.roots_for("gemini") == (gemini,)
    assert settings.roots_for("git") == (git,)
