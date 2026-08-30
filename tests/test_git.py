from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path

import orjson

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import GitAdapter


def _git(path: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    process = subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return process.stdout.strip()


def _commit(path: Path, filename: str, content: str, timestamp: str, message: str) -> str:
    (path / filename).write_text(content, encoding="utf-8")
    _git(path, "add", filename)
    return _git(
        path,
        "commit",
        "-m",
        message,
        env={"GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp},
    )


def _git_fixture(root: Path) -> tuple[Path, Path, str, str]:
    frontend = root / "frontend"
    frontend.mkdir(parents=True)
    _git(frontend, "init", "-b", "main")
    _git(frontend, "config", "user.name", "Fixture Author")
    _git(frontend, "config", "user.email", "fixture@example.test")
    _commit(frontend, "widget.txt", "one\n", "2025-05-11T04:26:55+08:00", "Add widget")
    shared_hash = _git(frontend, "rev-parse", "HEAD")
    _git(frontend, "remote", "add", "origin", "git@github.com:Example/frontend.git")

    spatial = root / "spatial"
    subprocess.run(
        ["git", "clone", "--no-local", str(frontend), str(spatial)],
        capture_output=True,
        text=True,
        check=True,
    )
    _git(spatial, "config", "user.name", "Fixture Author")
    _git(spatial, "config", "user.email", "fixture@example.test")
    _git(spatial, "remote", "set-url", "origin", "https://github.com/Example/spatial.git")
    _commit(spatial, "spatial.txt", "two\n", "2026-07-18T18:12:41+08:00", "Add spatial model")
    spatial_hash = _git(spatial, "rev-parse", "HEAD")
    return frontend, spatial, shared_hash, spatial_hash


def _records(source: Path) -> list[dict]:
    return [orjson.loads(line) for line in source.read_bytes().splitlines()]


def test_git_discovers_projects_preserves_lineage_and_is_idempotent(tmp_path: Path) -> None:
    projects = tmp_path / "Projects"
    frontend, spatial, shared_hash, spatial_hash = _git_fixture(projects)
    archive = tmp_path / "state" / "git-sources"
    adapter = GitAdapter(projects, archive)

    sources = adapter.prepare()
    assert len(sources) == 2
    assert all(source.provenance["git_root"] == str(projects) for source in sources)
    by_remote = {}
    for source in sources:
        records = _records(source.path)
        by_remote[records[0]["repository"]["repository_url"]] = (source, records)

    frontend_source, frontend_records = by_remote["https://github.com/example/frontend"]
    _, spatial_records = by_remote["https://github.com/example/spatial"]
    frontend_commit = next(
        record for record in frontend_records if record.get("commit", {}).get("hash") == shared_hash
    )
    inherited = next(
        record for record in spatial_records if record.get("commit", {}).get("hash") == shared_hash
    )
    spatial_commit = next(
        record for record in spatial_records if record.get("commit", {}).get("hash") == spatial_hash
    )
    assert frontend_commit["record_type"] == "commit"
    assert frontend_commit["workload_eligible"] is True
    assert inherited["record_type"] == "inherited_commit"
    assert inherited["workload_eligible"] is False
    assert spatial_commit["record_type"] == "commit"
    assert spatial_commit["commit"]["changes"] == [{"path": "spatial.txt", "status": "A"}]
    assert any(record["record_type"] == "reflog" for record in spatial_records)

    source_spec = next(source for source in sources if source.path == frontend_source.path)
    parsed = adapter.parse(frontend_commit, source_spec)
    assert parsed.timestamp == "2025-05-11T04:26:55+08:00"
    assert parsed.cwd == str(frontend)
    assert parsed.provider_event_id == f"git:commit:{shared_hash}"
    inherited_parsed = adapter.parse(inherited, source_spec)
    assert inherited_parsed.timestamp is None

    mtimes = {source.path: source.path.stat().st_mtime_ns for source in sources}
    second = adapter.prepare()
    assert [source.path for source in second] == [source.path for source in sources]
    assert {source.path: source.path.stat().st_mtime_ns for source in second} == mtimes
    assert adapter.discover() == sources
    assert spatial.is_dir()


def test_git_sync_retains_raw_records_and_opens_new_revision(corpus, tmp_path: Path) -> None:
    settings, _, _ = corpus
    assert settings.database_url not in repr(settings)
    projects = tmp_path / "Projects-live"
    frontend, _, shared_hash, _ = _git_fixture(projects)
    settings = replace(settings, git_root=projects)
    adapter = GitAdapter(projects, settings.git_sources_dir)
    adapter.prepare()
    ingestor = Ingestor(settings, [adapter], batch_lines=20)

    first = ingestor.run(providers={"git"})
    assert first.discovered_files == 2
    assert first.processed_files == 2
    assert first.parse_errors == 0
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources WHERE provider='git'").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE provider_event_id=? AND timestamp IS NOT NULL",
            (f"git:commit:{shared_hash}",),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM project_aliases WHERE provider IS NULL AND path_prefix=?",
            (str(frontend),),
        ).fetchone()[0] == 1
        raw_count = connection.execute(
            """
            SELECT COUNT(*) FROM raw_records raw
            JOIN source_revisions revision ON revision.id=raw.source_revision_id
            JOIN sources source ON source.id=revision.source_id
            WHERE source.provider='git'
            """
        ).fetchone()[0]
        assert raw_count > 2

    adapter.prepare()
    second = ingestor.run(providers={"git"})
    assert second.skipped_files == 2
    assert second.events == 0

    with database(settings.database_url) as connection:
        connection.execute(
            """
            UPDATE source_revisions SET provenance_json='{}'::jsonb
            WHERE id=(
                SELECT active_revision_id FROM sources
                WHERE provider='git' AND path=?
            )
            """,
            (str(adapter.discover()[0].path),),
        )
    repaired = ingestor.run(providers={"git"})
    assert repaired.processed_files == 1
    assert repaired.reparsed_files == 1
    assert ingestor.run(providers={"git"}).skipped_files == 2

    _commit(frontend, "later.txt", "later\n", "2026-08-20T10:00:00+08:00", "Add later work")
    adapter.prepare()
    changed = ingestor.run(providers={"git"})
    assert changed.processed_files == 1
    assert changed.reparsed_files == 1
    with database(settings.database_url, read_only=True) as connection:
        revisions = connection.execute(
            """
            SELECT COUNT(*) FROM source_revisions revision
            JOIN sources source ON source.id=revision.source_id
            WHERE source.provider='git'
            """
        ).fetchone()[0]
        assert revisions == 4
