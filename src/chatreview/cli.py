from __future__ import annotations

import importlib.util
import ipaddress
import json
import os
import platform
import secrets
import shlex
import subprocess
import sys
import textwrap
import webbrowser
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

import typer

from chatreview.api import create_app
from chatreview.automation import automation_status
from chatreview.config import Settings, default_settings
from chatreview.db import (
    close_pools,
    database,
    migrate,
    rebuild_lexical_indexes,
    rebuild_search_indexes,
    suspend_search_indexes,
)
from chatreview.db import doctor as database_doctor
from chatreview.episodes import EpisodeBuilder, write_episode_summary
from chatreview.exporter import collect_evidence, write_export
from chatreview.ingest import sync_sources
from chatreview.inventory import build_inventory, write_inventory
from chatreview.providers import ClaudeAdapter, CodexAdapter, GeminiAdapter, GitAdapter
from chatreview.reporting import build_baseline_report, write_baseline_report
from chatreview.resume import (
    ProviderResumeModel,
    ResumeError,
    ResumeSurfaceRefresher,
    list_resume_surfaces,
)
from chatreview.review import available_labels, build_review_queue, save_review
from chatreview.search import SearchFilters, lexical_search, reciprocal_rank_fusion
from chatreview.semantic import (
    DEFAULT_MODEL as DEFAULT_EMBEDDING_MODEL,
)
from chatreview.semantic import (
    DEFAULT_MODEL_REVISION,
    DeriveOptions,
    SemanticDeriver,
    SemanticSearchService,
    list_semantic_runs,
)
from chatreview.source_selection import HistoryScope
from chatreview.summary_providers import SummaryProviderError, provider_from_environment
from chatreview.timesheets import (
    TimesheetFilters,
    build_timesheet,
    export_timesheet,
    financial_year_dates,
)
from chatreview.worker import run_cycle, run_forever

app = typer.Typer(
    name="open-chat-reviewer",
    help="Archive, search, summarize, and review local AI chats and Git activity.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
db_app = typer.Typer(help="Inspect and migrate PostgreSQL.")
resume_app = typer.Typer(help="Build and inspect evidence-bounded resume cards.")
semantic_app = typer.Typer(help="Build and inspect optional semantic indexes.")
timesheets_app = typer.Typer(help="Build and export overlap-aware workload intervals.")
worker_app = typer.Typer(help="Run repeatable sync and derivation cycles.")
app.add_typer(db_app, name="db")
app.add_typer(resume_app, name="resume")
app.add_typer(semantic_app, name="semantic")
app.add_typer(timesheets_app, name="timesheets")
app.add_typer(worker_app, name="worker")

DataDir = Annotated[
    Path | None,
    typer.Option("--data-dir", help="Runtime state directory (default: ./.chatreview)."),
]
CodexRoot = Annotated[Path | None, typer.Option("--codex-root", help="Codex home/history root.")]
ClaudeRoot = Annotated[
    Path | None, typer.Option("--claude-root", help="Claude home/history root.")
]
GeminiRoot = Annotated[
    Path | None, typer.Option("--gemini-root", help="Gemini CLI home/history root.")
]
GitRoot = Annotated[
    Path | None,
    typer.Option("--git-root", help="Root containing recursively discovered Git repositories."),
]


@app.callback()
def _close_database_pools(context: typer.Context) -> None:
    """Release PostgreSQL pools deterministically after each command."""

    context.call_on_close(close_pools)


def _settings(
    data_dir: Path | None,
    codex_root: Path | None,
    claude_root: Path | None,
    gemini_root: Path | None = None,
    git_root: Path | None = None,
) -> Settings:
    return default_settings(
        data_dir=data_dir,
        codex_root=codex_root,
        claude_root=claude_root,
        gemini_root=gemini_root,
        git_root=git_root,
    )


def _adapters(settings: Settings, *, include_git: bool) -> list:
    adapters = [
        CodexAdapter(settings.codex_root),
        ClaudeAdapter(settings.claude_root),
        GeminiAdapter(settings.gemini_root),
    ]
    if include_git:
        adapters.append(GitAdapter(settings.git_root, settings.git_sources_dir))
    return adapters


def _provider_selection(provider: list[str] | None, *, include_git: bool) -> set[str] | None:
    allowed = {"codex", "claude", "gemini", "git"}
    selected = set(provider or ())
    invalid = selected - allowed
    if invalid:
        raise typer.BadParameter(
            f"unknown provider(s): {', '.join(sorted(invalid))}; "
            "use codex, claude, gemini, or git"
        )
    if selected:
        if not include_git:
            selected.discard("git")
        return selected
    return None if include_git else {"codex", "claude", "gemini"}


def _tailscale_identity() -> tuple[str, str] | None:
    """Return the active Tailscale IPv4 and preferred MagicDNS name, if available."""

    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    addresses = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(addresses) != 1:
        return None
    try:
        address = ipaddress.ip_address(addresses[0])
    except ValueError:
        return None
    if address.version != 4 or address.is_loopback:
        return None

    hostname = str(address)
    try:
        status = subprocess.run(
            ["tailscale", "status", "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        payload = json.loads(status.stdout)
        dns_name = str(payload.get("Self", {}).get("DNSName", "")).rstrip(".")
        if payload.get("CurrentTailnet", {}).get("MagicDNSEnabled") and dns_name:
            hostname = dns_name
    except (json.JSONDecodeError, FileNotFoundError, subprocess.SubprocessError):
        pass
    return str(address), hostname


@app.command("init")
def initialize(
    output: Annotated[
        Path,
        typer.Option("--output", help="Environment file to create."),
    ] = Path(".chatreview/archive.env"),
    database_url: Annotated[
        str | None,
        typer.Option(help="PostgreSQL URL written to the local environment file."),
    ] = None,
    role: Annotated[
        Literal["central", "writer"],
        typer.Option(help="Central nodes host the UI/database; writer nodes only ingest local sources."),
    ] = "central",
    network: Annotated[
        Literal["auto", "tailscale", "loopback"],
        typer.Option(
            help="Central-node bind policy. Auto prefers an active Tailscale interface."
        ),
    ] = "auto",
) -> None:
    """Create private central-node or remote-writer configuration."""

    if output.exists():
        typer.echo(f"Refusing to overwrite existing configuration: {output}", err=True)
        raise typer.Exit(2)
    if role == "writer":
        database_url = database_url or os.environ.get("CHATREVIEW_DATABASE_URL")
        if not database_url:
            raise typer.BadParameter(
                "writer nodes require --database-url or CHATREVIEW_DATABASE_URL"
            )
        network_values: dict[str, str] = {}
    else:
        identity = None if network == "loopback" else _tailscale_identity()
        if network == "tailscale" and identity is None:
            raise typer.BadParameter(
                "--network tailscale requires one active Tailscale IPv4 address"
            )
        bind_address, public_host = identity or ("127.0.0.1", "127.0.0.1")
        network_values = {
            "CHATREVIEW_DB_BIND_ADDRESS": bind_address,
            "CHATREVIEW_DB_PORT": "54329",
            "CHATREVIEW_PUBLIC_DATABASE_HOST": public_host,
            "CHATREVIEW_WEB_TAILSCALE_ONLY": "1" if identity else "0",
        }
        if database_url is None:
            password = secrets.token_hex(24)
            database_url = (
                f"postgresql://chatreview:{password}@{bind_address}:54329/chatreview"
            )
            network_values["CHATREVIEW_POSTGRES_PASSWORD"] = password

    output.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "CHATREVIEW_DATABASE_URL": database_url,
        "CHATREVIEW_MACHINE_ID": str(uuid4()),
        "CHATREVIEW_MACHINE_NAME": platform.node() or "local-machine",
        "CHATREVIEW_NODE_ROLE": role,
        "CHATREVIEW_CODEX_ROOT": str(Path.home() / ".codex"),
        "CHATREVIEW_CLAUDE_ROOT": str(Path.home() / ".claude"),
        "CHATREVIEW_GEMINI_ROOT": str(Path.home() / ".gemini"),
        "CHATREVIEW_GIT_ROOT": str(Path.home() / "Projects"),
        "CHATREVIEW_ENABLE_GIT": "1",
        "CHATREVIEW_ENABLE_SUMMARIES": "0",
        **network_values,
    }
    content = "\n".join(f"export {key}={shlex.quote(value)}" for key, value in values.items()) + "\n"
    output.write_text(content, encoding="utf-8")
    output.chmod(0o600)
    typer.echo(f"Created {output} with mode 600.")
    if role == "writer":
        typer.echo(f"Next: source {output} && uv run open-chat-reviewer db doctor")
        typer.echo("Then run scripts/chatreview-sync.sh; do not run migrations from a writer node.")
    else:
        if network_values["CHATREVIEW_WEB_TAILSCALE_ONLY"] == "1":
            typer.echo(
                "Selected the active Tailscale interface for the bundled database and web UI."
            )
        typer.echo(
            f"Next: source {output} && docker compose up -d db && "
            "uv run open-chat-reviewer db migrate"
        )


def _doctor(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
) -> None:
    settings = _settings(data_dir, codex_root, claude_root, gemini_root, git_root)
    checks: list[tuple[str, bool, str, bool]] = [
        ("Python >= 3.12", sys.version_info >= (3, 12), sys.version.split()[0], True),
        (
            "Codex sessions",
            (settings.codex_root / "sessions").is_dir(),
            str(settings.codex_root),
            False,
        ),
        (
            "Claude projects",
            (settings.claude_root / "projects").is_dir(),
            str(settings.claude_root),
            False,
        ),
        (
            "Gemini conversations",
            bool(GeminiAdapter(settings.gemini_root).discover()),
            str(settings.gemini_root),
            False,
        ),
        ("Git projects", settings.git_root.is_dir(), str(settings.git_root), False),
    ]
    try:
        report = database_doctor(settings.database_url)
        database_ok = {"vector", "pg_trgm"}.issubset(report.extensions)
        detail = (
            f"PostgreSQL {report.server_version}; {report.database}; "
            f"vector {report.extensions.get('vector', 'missing')}; "
            f"pg_trgm {report.extensions.get('pg_trgm', 'missing')}; "
            f"{report.migration_count} migrations"
        )
        checks.append(("PostgreSQL archive", database_ok, detail, True))
    except Exception as exc:
        checks.append(("PostgreSQL archive", False, f"{type(exc).__name__}: {exc}", True))
    semantic_modules = all(
        importlib.util.find_spec(name) is not None
        for name in ("hdbscan", "sentence_transformers", "umap")
    )
    checks.append(
        (
            "Semantic dependencies",
            semantic_modules,
            "installed" if semantic_modules else "optional: uv sync --extra semantic",
            False,
        )
    )
    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist" / "index.html"
    checks.append(("Browser assets", web_dist.is_file(), str(web_dist), False))
    failures = 0
    for name, passed, detail, required in checks:
        marker = "OK" if passed else "FAIL" if required else "INFO"
        typer.echo(f"[{marker:4}] {name}: {detail}")
        failures += int(required and not passed)
    if failures:
        raise typer.Exit(1)


@app.command()
def doctor(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
) -> None:
    """Check PostgreSQL, source roots, optional search support, and UI assets."""

    _doctor(data_dir, codex_root, claude_root, gemini_root, git_root)


@db_app.command("doctor")
def db_doctor(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
) -> None:
    """Check database connectivity and the surrounding installation."""

    _doctor(data_dir, codex_root, claude_root, gemini_root, git_root)


@db_app.command("migrate")
def db_migrate(data_dir: DataDir = None) -> None:
    """Apply ordered, checksum-guarded PostgreSQL migrations."""

    applied = migrate(_settings(data_dir, None, None).database_url)
    typer.echo(
        f"Applied {len(applied)} migration(s): "
        f"{', '.join(applied) if applied else 'already current'}."
    )


@db_app.command("suspend-search-indexes")
def db_suspend_search_indexes(data_dir: DataDir = None) -> None:
    """Drop reproducible indexes before a very large initial import."""

    changed = suspend_search_indexes(_settings(data_dir, None, None).database_url)
    typer.echo(f"Suspended {len(changed)} reproducible search indexes.")


@db_app.command("rebuild-search-indexes")
def db_rebuild_search_indexes(data_dir: DataDir = None) -> None:
    """Concurrently rebuild lexical, trigram, and vector indexes."""

    changed = rebuild_search_indexes(_settings(data_dir, None, None).database_url)
    typer.echo(f"Rebuilt {len(changed)} reproducible search indexes.")


@db_app.command("rebuild-lexical-indexes")
def db_rebuild_lexical_indexes(data_dir: DataDir = None) -> None:
    """Concurrently rebuild only lexical and trigram indexes."""

    changed = rebuild_lexical_indexes(_settings(data_dir, None, None).database_url)
    typer.echo(f"Rebuilt {len(changed)} lexical and trigram indexes.")


@app.command()
def inventory(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
    include_git: Annotated[
        bool,
        typer.Option("--git/--no-git", envvar="CHATREVIEW_ENABLE_GIT"),
    ] = True,
    deep: Annotated[bool, typer.Option(help="Inspect all records rather than a sample.")] = False,
    sample_lines: Annotated[int, typer.Option(min=1)] = 200,
) -> None:
    """Profile discovered chat files, optional Git evidence, and current coverage."""

    settings = _settings(data_dir, codex_root, claude_root, gemini_root, git_root)
    adapters = _adapters(settings, include_git=include_git)
    for adapter in adapters:
        prepare = getattr(adapter, "prepare", None)
        if callable(prepare):
            prepare()
    report = build_inventory(settings, adapters, deep=deep, sample_lines=sample_lines)
    json_path, markdown_path = write_inventory(settings, report)
    typer.echo(f"Discovered {report['total_files']:,} files / {_human_bytes(report['total_bytes'])}.")
    typer.echo(f"JSON: {json_path}")
    typer.echo(f"Markdown: {markdown_path}")


@app.command("ingest", deprecated=True)
@app.command("sync")
def sync_command(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
    provider: Annotated[list[str] | None, typer.Option("--provider")] = None,
    include_git: Annotated[
        bool,
        typer.Option("--git/--no-git", envvar="CHATREVIEW_ENABLE_GIT"),
    ] = True,
    force: Annotated[bool, typer.Option()] = False,
    batch_lines: Annotated[int, typer.Option(min=10)] = 1000,
    progress_every: Annotated[int, typer.Option(min=1)] = 25,
    workers: Annotated[int, typer.Option(min=1)] = 1,
    shard_index: Annotated[int, typer.Option(min=0)] = 0,
    shard_count: Annotated[int, typer.Option(min=1)] = 1,
    history_since: Annotated[
        str | None,
        typer.Option(
            "--history-since",
            help="Include conversation sources from this UTC date (YYYY-MM-DD), inclusive.",
        ),
    ] = None,
    history_until: Annotated[
        str | None,
        typer.Option(
            "--history-until",
            help="Include conversation sources through this UTC date (YYYY-MM-DD), inclusive.",
        ),
    ] = None,
) -> None:
    """Incrementally sync read-only source directories into PostgreSQL."""

    settings = _settings(data_dir, codex_root, claude_root, gemini_root, git_root)
    providers = _provider_selection(provider, include_git=include_git)
    if shard_index >= shard_count:
        raise typer.BadParameter("--shard-index must be less than --shard-count")
    if workers > 1 and (shard_index != 0 or shard_count != 1):
        raise typer.BadParameter("--workers cannot be combined with explicit shard options")
    try:
        history_scope = HistoryScope(history_since, history_until)
    except (TypeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if (providers is None or "gemini" in providers) and not GeminiAdapter(
        settings.gemini_root
    ).discover():
        typer.echo(
            "Gemini: no local session/history documents were found; if Gemini CLI did not "
            "retain them, an export or supported API source is required."
        )
    summary = sync_sources(
        settings,
        providers=providers,
        force=force,
        batch_lines=batch_lines,
        progress_every=progress_every,
        workers=workers,
        shard_index=shard_index,
        shard_count=shard_count,
        history_since=history_scope.since,
        history_until=history_scope.until,
        progress=typer.echo,
    )
    if history_scope.active:
        typer.echo(
            "History scope: "
            f"{history_scope.since or 'earliest'} through {history_scope.until or 'latest'}; "
            f"{summary.excluded_files:,} sources excluded before persistence; "
            f"{summary.aggregate_files:,} aggregate history files retained; "
            f"{summary.mtime_bound_files:,} sources selected/bounded by UTC mtime."
        )
    typer.echo(
        "Sync complete: "
        f"{summary.processed_files:,} processed, {summary.skipped_files:,} unchanged, "
        f"{summary.events:,} events, {summary.text_units:,} text units, "
        f"{summary.parse_errors:,} parse errors, {_human_bytes(summary.bytes_read)} read."
    )


@app.command("episodes")
def episodes_command(
    data_dir: DataDir = None,
    force: Annotated[bool, typer.Option()] = False,
) -> None:
    """Derive incremental goal-attempt-result episodes from canonical events."""

    settings = _settings(data_dir, None, None)
    summary = EpisodeBuilder(settings, progress=typer.echo).run(force=force)
    output = settings.reports_dir / "episode-derivation.md"
    write_episode_summary(output, summary)
    typer.echo(
        f"Episodes: {summary.episodes:,}; {summary.rebuilt_sessions:,} sessions rebuilt, "
        f"{summary.reused_sessions:,} reused. Report: {output}"
    )


@app.command("refresh")
def refresh_command(
    data_dir: DataDir = None,
    force: Annotated[bool, typer.Option()] = False,
) -> None:
    """Refresh deterministic episodes and workload intervals after a sync."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url, read_only=True) as connection:
        before = automation_status(connection)
    if not before["refresh"]["safe"]:
        typer.echo("Refresh blocked: " + "; ".join(before["blocking_reasons"]), err=True)
        raise typer.Exit(75)
    actions: list[str] = []
    if force or before["refresh"]["needs_episodes"]:
        result = EpisodeBuilder(settings, progress=typer.echo).run(force=force)
        actions.append("episodes(reused)" if result.reused else "episodes")
    with database(settings.database_url, read_only=True) as connection:
        after_episodes = automation_status(connection)
    if force or after_episodes["refresh"]["needs_timesheet"]:
        with database(settings.database_url) as connection:
            result = build_timesheet(connection, cutoff=datetime.now(UTC), force=force)
        actions.append("timesheet(reused)" if result.reused else "timesheet")
    typer.echo("Refresh complete: " + (", ".join(actions) if actions else "already current"))


@resume_app.command("refresh")
def resume_refresh_command(
    data_dir: DataDir = None,
    days: Annotated[int, typer.Option(min=1, max=365)] = 30,
    hours: Annotated[int | None, typer.Option(min=1, max=8760)] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 40,
    per_project_limit: Annotated[int, typer.Option(min=1, max=20)] = 3,
    provider: Annotated[str | None, typer.Option(help="Provider kind override.")] = None,
    model: Annotated[str | None, typer.Option(help="Model identifier override.")] = None,
    base_url: Annotated[str | None, typer.Option(help="Provider base URL override.")] = None,
    force: Annotated[bool, typer.Option()] = False,
) -> None:
    """Summarize recent work threads through the configured model provider."""

    settings = _settings(data_dir, None, None)
    try:
        model_adapter = ProviderResumeModel(
            provider_from_environment(
                provider=provider,
                model_name=model,
                base_url=base_url,
            )
        )
        summary = ResumeSurfaceRefresher(
            settings.database_url,
            model_adapter,
            progress=typer.echo,
        ).run(
            days=days,
            hours=hours,
            limit=limit,
            per_project_limit=per_project_limit,
            force=force,
        )
    except (ResumeError, SummaryProviderError) as exc:
        typer.echo(f"Resume refresh failed: {exc}", err=True)
        raise typer.Exit(75) from exc
    typer.echo(
        f"Resume refresh {summary.status}: {summary.generated:,} generated, "
        f"{summary.reused:,} reused, {summary.failed:,} failed."
    )


@resume_app.command("status")
def resume_status_command(
    data_dir: DataDir = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 200,
) -> None:
    """Print the current public resume-card payload."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url, read_only=True) as connection:
        result = list_resume_surfaces(connection, limit=limit)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@semantic_app.command("refresh")
def semantic_refresh_command(
    data_dir: DataDir = None,
    profile: Annotated[Literal["conversation", "episodes"], typer.Option()] = "conversation",
    model: Annotated[str, typer.Option()] = DEFAULT_EMBEDDING_MODEL,
    model_revision: Annotated[str, typer.Option()] = DEFAULT_MODEL_REVISION,
    dimensions: Annotated[int, typer.Option(min=32, max=4096)] = 512,
    window_chars: Annotated[int, typer.Option(min=500, max=50_000)] = 6000,
    overlap_events: Annotated[int, typer.Option(min=0, max=20)] = 1,
    batch_size: Annotated[int, typer.Option(min=1, max=1024)] = 16,
    device: Annotated[str | None, typer.Option()] = None,
    offline: Annotated[bool, typer.Option()] = False,
    force: Annotated[bool, typer.Option()] = False,
) -> None:
    """Build an optional pgvector semantic index and projection."""

    settings = _settings(data_dir, None, None)
    summary = SemanticDeriver(settings, progress=typer.echo).run(
        DeriveOptions(
            profile=profile,
            model_name=model,
            model_revision=model_revision,
            dimensions=dimensions,
            window_chars=window_chars,
            overlap_events=overlap_events,
            batch_size=batch_size,
            device=device,
            offline=offline,
            force=force,
        )
    )
    typer.echo(
        f"Semantic run {summary.run_key}: {summary.windows:,} windows, "
        f"{summary.clusters:,} clusters{' (reused)' if summary.reused else ''}."
    )


@semantic_app.command("status")
def semantic_status_command(data_dir: DataDir = None) -> None:
    """List available semantic runs."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url, read_only=True) as connection:
        result = list_semantic_runs(connection)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command("status")
def status_command(data_dir: DataDir = None) -> None:
    """Print archive, freshness, and next-action status as JSON."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url, read_only=True) as connection:
        result = automation_status(connection)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@app.command("search")
def search_command(
    query: Annotated[str, typer.Argument()],
    data_dir: DataDir = None,
    mode: Annotated[Literal["lexical", "semantic", "hybrid"], typer.Option()] = "lexical",
    provider: Annotated[str | None, typer.Option()] = None,
    project: Annotated[str | None, typer.Option()] = None,
    role: Annotated[str | None, typer.Option()] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
) -> None:
    """Search exact indexed text, optional embeddings, or both."""

    settings = _settings(data_dir, None, None)
    filters = SearchFilters(provider=provider, project=project, role=role)
    with database(settings.database_url, read_only=True) as connection:
        lexical = lexical_search(connection, query, filters=filters, limit=limit)
        semantic = []
        if mode in {"semantic", "hybrid"}:
            semantic = SemanticSearchService(settings).search(
                connection,
                query,
                filters=filters,
                limit=limit,
            )
    results = (
        reciprocal_rank_fusion(lexical, semantic, limit=limit)
        if mode == "hybrid"
        else lexical if mode == "lexical" else semantic
    )
    typer.echo(json.dumps({"query": query, "mode": mode, "results": results}, indent=2, default=str))


@app.command("review")
def review_command(
    data_dir: DataDir = None,
    query: Annotated[str | None, typer.Option("--query", "-q")] = None,
    mode: Annotated[Literal["lexical", "semantic", "hybrid"], typer.Option()] = "lexical",
    limit: Annotated[int, typer.Option(min=1, max=500)] = 50,
    include_reviewed: Annotated[bool, typer.Option()] = False,
) -> None:
    """Step through a terminal review queue and apply stable labels."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url) as connection:
        queue = build_review_queue(
            connection,
            settings,
            query=query,
            mode=mode,
            limit=limit,
            unreviewed_only=not include_reviewed,
        )
        if not queue:
            typer.echo("No matching review evidence was found.")
            return
        labels = {row["name"] for row in available_labels(connection)}
        typer.echo("Enter a label name, 'note', 'skip', or 'quit'.")
        for position, item in enumerate(queue, start=1):
            typer.echo(f"\n[{position}/{len(queue)}] {item['provider']} · {item['heading']}")
            typer.echo(textwrap.shorten(str(item["preview"]), width=2_000, placeholder=" …"))
            action = typer.prompt("Action", default="skip").strip()
            if action == "quit":
                return
            if action == "skip":
                continue
            label = None if action == "note" else action
            if label is not None and label not in labels:
                typer.echo("Unknown label; skipped.")
                continue
            note = typer.prompt("Note (optional)", default="", show_default=False)
            save_review(
                connection,
                target_type=item["target_type"],
                target_key=item["target_key"],
                label=label,
                note=note or None,
            )


@app.command("annotate")
def annotate_command(
    target_type: Annotated[Literal["session", "event", "window", "episode"], typer.Argument()],
    target_key: Annotated[str, typer.Argument()],
    data_dir: DataDir = None,
    label: Annotated[str | None, typer.Option()] = None,
    note: Annotated[str | None, typer.Option()] = None,
    state: Annotated[Literal["unreviewed", "reviewing", "reviewed"], typer.Option()] = "reviewed",
) -> None:
    """Apply one label or note to a stable archive target."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url) as connection:
        try:
            saved = save_review(
                connection,
                target_type=target_type,
                target_key=target_key,
                label=label,
                note=note,
                review_state=state,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(saved, indent=2, default=str))


@app.command("list-labels")
def list_labels(data_dir: DataDir = None) -> None:
    """List the review label taxonomy and usage counts."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url, read_only=True) as connection:
        labels = available_labels(connection)
    typer.echo(json.dumps(labels, indent=2, default=str))


@app.command("export")
def export_command(
    output: Annotated[Path, typer.Argument()],
    data_dir: DataDir = None,
    query: Annotated[str | None, typer.Option("--query", "-q")] = None,
    session_id: Annotated[int | None, typer.Option()] = None,
    label: Annotated[str | None, typer.Option()] = None,
    format: Annotated[Literal["markdown", "jsonl", "csv"], typer.Option()] = "markdown",
    limit: Annotated[int, typer.Option(min=1, max=5000)] = 1000,
) -> None:
    """Export a selected, provenance-linked evidence set."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url, read_only=True) as connection:
        try:
            records = collect_evidence(
                connection,
                query=query,
                session_id=session_id,
                label=label,
                limit=limit,
            )
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    write_export(output, records, format)
    typer.echo(f"Wrote {len(records):,} records to {output}.")


@app.command("report")
def report_command(
    data_dir: DataDir = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    top: Annotated[int, typer.Option(min=1, max=200)] = 30,
    min_sessions: Annotated[int, typer.Option(min=1)] = 2,
) -> None:
    """Generate a baseline archive review without model-authored causality."""

    settings = _settings(data_dir, None, None)
    output = output or settings.reports_dir / "baseline-review.md"
    with database(settings.database_url, read_only=True) as connection:
        content = build_baseline_report(connection, top=top, min_sessions=min_sessions)
    write_baseline_report(output, content)
    typer.echo(f"Wrote baseline review report to {output}.")


@timesheets_app.command("build")
def timesheets_build(
    data_dir: DataDir = None,
    cutoff: Annotated[datetime | None, typer.Option()] = None,
    force: Annotated[bool, typer.Option()] = False,
) -> None:
    """Build a versioned, overlap-aware activity interval snapshot."""

    settings = _settings(data_dir, None, None)
    with database(settings.database_url) as connection:
        summary = build_timesheet(connection, cutoff=cutoff or datetime.now(UTC), force=force)
    typer.echo(
        f"Timesheet {summary.snapshot_key}: {summary.intervals:,} intervals, "
        f"{summary.total_seconds / 3600:,.3f} hours."
    )


@timesheets_app.command("export")
def timesheets_export(
    output: Annotated[Path, typer.Argument()],
    data_dir: DataDir = None,
    format: Annotated[Literal["csv", "markdown", "json"], typer.Option()] = "csv",
    date_from: Annotated[str | None, typer.Option()] = None,
    date_to: Annotated[str | None, typer.Option()] = None,
    financial_year: Annotated[str | None, typer.Option("--financial-year")] = None,
    contributor: Annotated[str | None, typer.Option()] = None,
    project: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Export workload intervals plus a hash manifest."""

    settings = _settings(data_dir, None, None)
    try:
        parsed_from = date.fromisoformat(date_from) if date_from else None
        parsed_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise typer.BadParameter("dates must use YYYY-MM-DD") from exc
    if financial_year:
        fy_start, fy_end = financial_year_dates(financial_year)
        parsed_from = parsed_from or fy_start
        parsed_to = parsed_to or fy_end
    filters = TimesheetFilters(
        date_from=parsed_from,
        date_to=parsed_to,
        contributor=contributor,
        project=project,
    )
    with database(settings.database_url) as connection:
        result = export_timesheet(connection, format=format, filters=filters)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.content)
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(result.manifest, indent=2, sort_keys=True) + "\n")
    typer.echo(f"Wrote {output} and {manifest_path}.")


@worker_app.command("once")
def worker_once(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
    provider: Annotated[list[str] | None, typer.Option("--provider")] = None,
    include_git: Annotated[
        bool,
        typer.Option("--git/--no-git", envvar="CHATREVIEW_ENABLE_GIT"),
    ] = True,
    sync_workers: Annotated[int, typer.Option(min=1)] = 1,
    summaries: Annotated[
        bool | None,
        typer.Option("--summaries/--no-summaries", envvar="CHATREVIEW_ENABLE_SUMMARIES"),
    ] = None,
    summary_hours: Annotated[int, typer.Option(min=1, max=8760)] = 24,
) -> None:
    """Run one complete sync, episode, workload, and optional summary cycle."""

    settings = _settings(data_dir, codex_root, claude_root, gemini_root, git_root)
    result = run_cycle(
        settings,
        providers=_provider_selection(provider, include_git=include_git),
        sync_workers=sync_workers,
        summaries=summaries,
        summary_hours=summary_hours,
        progress=typer.echo,
    )
    typer.echo(json.dumps(asdict(result) if result else {"status": "already-running"}, indent=2, default=str))


@worker_app.command("run")
def worker_run(
    data_dir: DataDir = None,
    codex_root: CodexRoot = None,
    claude_root: ClaudeRoot = None,
    gemini_root: GeminiRoot = None,
    git_root: GitRoot = None,
    provider: Annotated[list[str] | None, typer.Option("--provider")] = None,
    include_git: Annotated[
        bool,
        typer.Option("--git/--no-git", envvar="CHATREVIEW_ENABLE_GIT"),
    ] = True,
    interval: Annotated[int, typer.Option(min=60, envvar="CHATREVIEW_SYNC_INTERVAL")] = 21_600,
    sync_workers: Annotated[int, typer.Option(min=1)] = 1,
    summaries: Annotated[
        bool | None,
        typer.Option("--summaries/--no-summaries", envvar="CHATREVIEW_ENABLE_SUMMARIES"),
    ] = None,
    summary_hours: Annotated[int, typer.Option(min=1, max=8760)] = 24,
) -> None:
    """Run complete cycles on an interval until SIGINT or SIGTERM."""

    settings = _settings(data_dir, codex_root, claude_root, gemini_root, git_root)
    run_forever(
        settings,
        interval_seconds=interval,
        providers=_provider_selection(provider, include_git=include_git),
        sync_workers=sync_workers,
        summaries=summaries,
        summary_hours=summary_hours,
        progress=typer.echo,
    )


@app.command("serve")
def serve(
    data_dir: DataDir = None,
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8765,
    open_browser: Annotated[bool, typer.Option("--open")] = False,
    reload: Annotated[bool, typer.Option()] = False,
) -> None:
    """Serve the local UI and read/write review API."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        typer.echo("Warning: this exposes private transcript data beyond loopback.")
    settings = _settings(data_dir, None, None)
    application = create_app(settings)
    if open_browser:
        import threading

        threading.Timer(0.8, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    import uvicorn

    uvicorn.run(application, host=host, port=port, reload=reload)


@app.command("build-web", hidden=True)
def build_web() -> None:
    """Build browser assets with the checked-in Bun lockfile."""

    web_dir = Path(__file__).resolve().parents[2] / "web"
    subprocess.run(["bun", "install", "--frozen-lockfile"], cwd=web_dir, check=True)
    subprocess.run(["bun", "run", "build"], cwd=web_dir, check=True)


def _human_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TiB"


if __name__ == "__main__":
    app()
