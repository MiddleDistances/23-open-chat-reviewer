from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from chatreview.source_roots import (
    MAX_ROOTS_PER_PROVIDER,
    SUPPORTED_PROVIDERS,
    SourceRootConfigurationError,
    load_source_roots,
    normalize_source_roots,
    records_to_source_roots,
    save_source_roots,
    source_roots_path,
    source_roots_to_records,
)


def test_save_load_round_trip_uses_full_mapping_and_private_permissions(tmp_path: Path) -> None:
    data_dir = tmp_path / ".chatreview"
    roots = {
        "codex": ["~/chat archives/codex"],
        "claude": [],
        "gemini": [str(tmp_path / "gemini")],
        "git": [],
    }

    saved = save_source_roots(data_dir, roots)
    loaded = load_source_roots(data_dir)
    path = source_roots_path(data_dir)

    assert loaded == saved
    assert list(saved) == list(SUPPORTED_PROVIDERS)
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "roots": saved}


def test_paths_with_spaces_and_colons_are_preserved_after_normalization(tmp_path: Path) -> None:
    source = tmp_path / "archive: with spaces"

    result = normalize_source_roots({"codex": [str(source)]})

    assert result["codex"] == [str(source.resolve())]


def test_duplicate_normalized_paths_keep_first_order(tmp_path: Path) -> None:
    source = tmp_path / "codex"
    alias = source / ".." / source.name

    result = normalize_source_roots({"codex": [str(source), str(alias), str(source)]})

    assert result["codex"] == [str(source.resolve())]


def test_explicit_empty_provider_lists_are_retained_and_missing_are_filled() -> None:
    result = normalize_source_roots({"claude": []})

    assert result == {provider: [] for provider in SUPPORTED_PROVIDERS}


def test_flat_record_helpers_round_trip_to_full_mapping(tmp_path: Path) -> None:
    records = [
        {"provider": "git", "path": str(tmp_path / "Projects")},
        {"provider": "codex", "path": str(tmp_path / "codex")},
        {"provider": "git", "path": str(tmp_path / "Projects")},
    ]

    mapping = records_to_source_roots(records)

    assert mapping["claude"] == []
    assert mapping["git"] == [str((tmp_path / "Projects").resolve())]
    assert source_roots_to_records(mapping) == [
        {"provider": "codex", "path": str((tmp_path / "codex").resolve())},
        {"provider": "git", "path": str((tmp_path / "Projects").resolve())},
    ]


@pytest.mark.parametrize(
    ("roots", "message"),
    [
        ([], "object"),
        ({"wat": []}, "unsupported"),
        ({"codex": "not-a-list"}, "list"),
        ({"codex": [""]}, "blank"),
        ({"codex": ["\x00bad"]}, "NUL"),
        ({"codex": ["x" * 4_097]}, "at most"),
    ],
)
def test_invalid_source_root_shapes_are_rejected(roots: object, message: str) -> None:
    with pytest.raises(SourceRootConfigurationError, match=message):
        normalize_source_roots(roots)  # type: ignore[arg-type]


def test_provider_limit_is_enforced_after_normalization(tmp_path: Path) -> None:
    roots = {"codex": [str(tmp_path / f"source-{index}") for index in range(MAX_ROOTS_PER_PROVIDER + 1)]}

    with pytest.raises(SourceRootConfigurationError, match="at most 16"):
        save_source_roots(tmp_path / ".chatreview", roots)


def test_load_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_source_roots(tmp_path / ".chatreview") is None


def test_load_rejects_invalid_document_and_provider(tmp_path: Path) -> None:
    data_dir = tmp_path / ".chatreview"
    data_dir.mkdir()
    path = source_roots_path(data_dir)
    path.write_text(json.dumps({"version": 1, "roots": {"wat": []}}), encoding="utf-8")

    with pytest.raises(SourceRootConfigurationError, match="unsupported"):
        load_source_roots(data_dir)

    path.write_text(json.dumps({"version": 1, "roots": []}), encoding="utf-8")
    with pytest.raises(SourceRootConfigurationError, match="object"):
        load_source_roots(data_dir)


def test_load_and_save_reject_symlink_configuration(tmp_path: Path) -> None:
    data_dir = tmp_path / ".chatreview"
    data_dir.mkdir()
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"version": 1, "roots": {}}), encoding="utf-8")
    path = source_roots_path(data_dir)
    path.symlink_to(target)

    with pytest.raises(SourceRootConfigurationError, match="regular file"):
        load_source_roots(data_dir)
    with pytest.raises(SourceRootConfigurationError, match="regular file"):
        save_source_roots(data_dir, {})


def test_load_rejects_dangling_symlink_instead_of_treating_it_as_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / ".chatreview"
    data_dir.mkdir()
    source_roots_path(data_dir).symlink_to(tmp_path / "does-not-exist.json")

    with pytest.raises(SourceRootConfigurationError, match="regular file"):
        load_source_roots(data_dir)


def test_save_rejects_unsupported_provider_before_writing(tmp_path: Path) -> None:
    data_dir = tmp_path / ".chatreview"

    with pytest.raises(SourceRootConfigurationError, match="unsupported"):
        save_source_roots(data_dir, {"openai": [str(tmp_path)]})

    assert not data_dir.exists()
