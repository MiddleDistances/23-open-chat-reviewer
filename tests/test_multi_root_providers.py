from __future__ import annotations

import os
import subprocess
from pathlib import Path

import orjson

from chatreview.providers import ClaudeAdapter, CodexAdapter, GeminiAdapter, GitAdapter


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(value) + b"\n")


def test_codex_discovers_multiple_roots_without_symlink_duplicates(tmp_path: Path) -> None:
    first_root = tmp_path / "codex-first"
    second_root = tmp_path / "codex-second"
    first_session = first_root / "sessions" / "2026" / "first.jsonl"
    second_session = second_root / "sessions" / "2026" / "second.jsonl"
    _write_json(first_session, {"type": "session_meta"})
    _write_json(second_session, {"type": "session_meta"})
    alias = tmp_path / "codex-alias"
    alias.symlink_to(first_root, target_is_directory=True)

    adapter = CodexAdapter([first_root, alias, second_root, first_root])

    assert adapter.roots == (first_root.resolve(), second_root.resolve())
    assert [source.path for source in adapter.discover()] == sorted(
        (first_session.resolve(), second_session.resolve())
    )


def test_claude_discovers_multiple_roots_without_symlink_duplicates(tmp_path: Path) -> None:
    first_root = tmp_path / "claude-first"
    second_root = tmp_path / "claude-second"
    first_session = first_root / "projects" / "first" / "session.jsonl"
    second_session = second_root / "projects" / "second" / "session.jsonl"
    _write_json(first_session, {"type": "user"})
    _write_json(second_session, {"type": "user"})
    alias = tmp_path / "claude-alias"
    alias.symlink_to(first_root, target_is_directory=True)

    adapter = ClaudeAdapter([first_root, alias, second_root, first_root])

    assert adapter.roots == (first_root.resolve(), second_root.resolve())
    assert [source.path for source in adapter.discover()] == sorted(
        (first_session.resolve(), second_session.resolve())
    )


def test_gemini_uses_each_root_projects_mapping(tmp_path: Path) -> None:
    first_root = tmp_path / "gemini-first"
    second_root = tmp_path / "gemini-second"
    first_storage = "first-project-storage"
    second_storage = "second-project-storage"
    _write_json(first_root / "projects.json", {"projects": {"/work/first": first_storage}})
    _write_json(second_root / "projects.json", {"projects": {"/work/second": second_storage}})
    first_session = first_root / "tmp" / first_storage / "chats" / "session-first.json"
    second_session = second_root / "tmp" / second_storage / "chats" / "session-second.json"
    _write_json(
        first_session,
        {"sessionId": "first-session", "projectHash": first_storage, "messages": []},
    )
    _write_json(
        second_session,
        {"sessionId": "second-session", "projectHash": second_storage, "messages": []},
    )

    sources = GeminiAdapter([first_root, second_root]).discover()

    assert {source.path for source in sources} == {
        first_session.resolve(),
        second_session.resolve(),
    }
    provenance_by_path = {source.path: source.provenance for source in sources}
    assert provenance_by_path[first_session.resolve()]["project_root"] == "/work/first"
    assert provenance_by_path[second_session.resolve()]["project_root"] == "/work/second"
    assert provenance_by_path[first_session.resolve()]["project_storage"] == first_storage
    assert provenance_by_path[second_session.resolve()]["project_storage"] == second_storage


def _run_git(path: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    process = subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return process.stdout.strip()


def _git_fixture(root: Path, name: str, timestamp: str) -> Path:
    repository = root / name
    repository.mkdir(parents=True)
    _run_git(repository, "init", "--quiet")
    _run_git(repository, "config", "user.name", "Multi Root Fixture")
    _run_git(repository, "config", "user.email", "multi-root@example.test")
    (repository / "README.md").write_text(f"{name}\n", encoding="utf-8")
    _run_git(repository, "add", "README.md")
    identity = {
        "GIT_AUTHOR_NAME": "Multi Root Fixture",
        "GIT_AUTHOR_EMAIL": "multi-root@example.test",
        "GIT_COMMITTER_NAME": "Multi Root Fixture",
        "GIT_COMMITTER_EMAIL": "multi-root@example.test",
        "GIT_AUTHOR_DATE": timestamp,
        "GIT_COMMITTER_DATE": timestamp,
    }
    _run_git(repository, "commit", "--quiet", "--no-gpg-sign", "-m", f"Add {name}", env=identity)
    return repository


def test_git_prepare_catalogs_and_rereads_multiple_roots(tmp_path: Path) -> None:
    first_root = tmp_path / "git-first"
    second_root = tmp_path / "git-second"
    first_repository = _git_fixture(first_root, "first-repository", "2026-08-30T10:00:00+00:00")
    second_repository = _git_fixture(second_root, "second-repository", "2026-08-30T11:00:00+00:00")
    archive = tmp_path / "git-sources"
    adapter = GitAdapter([first_root, second_root], archive)

    sources = adapter.prepare()
    assert len(sources) == 2
    assert {
        checkout
        for source in sources
        for checkout in source.provenance["checkout_paths"]
    } == {str(first_repository.resolve()), str(second_repository.resolve())}
    assert {source.provenance["git_root"] for source in sources} == {
        str(first_root.resolve()),
        str(second_root.resolve()),
    }

    catalog = orjson.loads((archive / "catalog.json").read_bytes())
    assert catalog["root"] == str(first_root.resolve())
    assert catalog["roots"] == [str(first_root.resolve()), str(second_root.resolve())]

    reread = GitAdapter([first_root, second_root], archive).discover()
    assert reread == sources
