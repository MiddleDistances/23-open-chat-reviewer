# Sync and worker operations

## One-time setup

```bash
uv sync
uv run open-chat-reviewer init
docker compose up -d db
uv run open-chat-reviewer db migrate
uv run open-chat-reviewer doctor
```

`init` writes `.chatreview/archive.env` with mode `0600`. Give every source machine a
stable, distinct `CHATREVIEW_MACHINE_ID`. Migrations are deliberate: the sync wrapper
runs the doctor but does not migrate unless `CHATREVIEW_SYNC_MIGRATE=1`.

Before a large first run, use the setup page or the inventory command to record the
intended archive scope: providers, roots, earliest date, Git metadata, and reasoning
retention policy. The archive scope belongs to each writer; it is valid for one machine
to contribute all available history while another contributes only a recent window.
The semantic scope is separate and can later be rebuilt with its own date, provider,
project, event-kind, and reasoning-inclusion policy. See [Setup, scope, and storage](SETUP_AND_STORAGE.md)
for the storage contract.

For several computers, host PostgreSQL and the derived worker on one central node and run
sync-only writers on the others. Do not share a machine ID or database password between
writers. See [Tailscale central archive and remote writers](TAILSCALE_MULTI_MACHINE.md).

## Incremental sync

```bash
scripts/chatreview-sync.sh
uv run open-chat-reviewer refresh
```

The wrapper loads the environment, refuses an empty discovery set, acquires a local
`flock`, checks PostgreSQL, and appends to `.chatreview/logs/sync-YYYYMMDD.log`. The
ingestor records source revisions and resumes from committed offsets. Re-running an
unchanged corpus is safe.

The wrapper is intentionally source-read-only. It writes PostgreSQL rows and local
runtime logs/locks only. It does not edit chat files, copy arbitrary checkout files, or
modify Git repositories. A successful sync updates the raw and canonical archive; it
does not imply that episodes, semantic windows, clusters, workload snapshots, or resume
cards are current.

Useful controls:

```bash
uv run open-chat-reviewer inventory --no-git
uv run open-chat-reviewer sync --provider codex --provider claude --workers 2
uv run open-chat-reviewer episodes --force
uv run open-chat-reviewer timesheets build --force
uv run open-chat-reviewer status
```

For an oversized initial import, the reproducible search indexes can be suspended and
rebuilt deliberately around the sync:

```bash
uv run open-chat-reviewer db suspend-search-indexes
scripts/chatreview-sync.sh
uv run open-chat-reviewer db rebuild-search-indexes
```

Use this only with sufficient disk headroom and a maintenance window. It changes index
maintenance, not the archive's raw evidence, and should be recorded in the run log.

Git discovery is enabled by default and can be disabled with
`CHATREVIEW_ENABLE_GIT=0` or `--no-git` where supported.

## Unattended worker

```bash
uv run open-chat-reviewer worker once
uv run open-chat-reviewer worker run --interval 21600
```

Each cycle checks and migrates the schema, acquires a PostgreSQL advisory lock, syncs
sources, refreshes episodes, refreshes a stale timesheet snapshot, and optionally refreshes
summary cards. The default six-hour interval is configurable with
`CHATREVIEW_SYNC_INTERVAL`.

Enable summaries only after configuring a provider:

```bash
export CHATREVIEW_ENABLE_SUMMARIES=1
export CHATREVIEW_SUMMARY_PROVIDER=openai-compatible
export CHATREVIEW_SUMMARY_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
export CHATREVIEW_SUMMARY_BASE_URL=http://127.0.0.1:8000/v1
```

Summaries are optional model-authored guidance and are kept separate from archive-derived
facts. They are not required for sync, lexical search, or the semantic map.

## Freshness contract

`sync` updates the raw and canonical archive. Episodes, semantic indexes, workload
snapshots, and resume cards are separate projections. `worker run` handles episodes,
timesheets, and optional summaries; semantic refreshes remain deliberate because model
downloads and GPU use can be substantial.

An initial sync can take substantially longer than a repeat sync because it parses every
selected source, writes raw and canonical rows, and maintains database indexes. Progress
is resumable: a process restart reuses completed source revisions and offsets. Use the
status view/command to distinguish files discovered, files processed, unchanged files,
parse failures, bytes written, and downstream projection freshness. Do not estimate
completion from the number of semantic points alone; the raw import and semantic build
are separate jobs.

Always check:

```bash
uv run open-chat-reviewer status
```

Missing semantic indexes and an empty optional activity catalog are reported but do not
make the core archive unhealthy. Failed sources, partial revisions, or stale required
projections do.

The semantic map has two independent date concepts. The semantic run's date scope
controls what was embedded; the map date filter narrows the displayed points from an
existing run without rebuilding it. Map tooltips show a short preview of the semantic
window text that was embedded, not a session headline. If a run includes readable
reasoning, its policy is shown with the run metadata.

## Recovery

1. Run `uv run open-chat-reviewer db doctor`.
2. Inspect the daily sync log and `uv run open-chat-reviewer status`.
3. Verify that source files are stable and readable; never edit them as recovery.
4. Re-run sync. Completed source offsets are reused.
5. Use `--force` only for a derived projection that must be rebuilt.

Back up PostgreSQL with normal `pg_dump`/restore tooling. The `.chatreview/` directory is
not a substitute for a database backup.

If a retry is needed, preserve the same machine ID and source roots. Re-running sync is
the normal recovery path. A broader history date range or changed reasoning policy is a
new explicit scope choice; it should be previewed before starting and does not silently
delete prior raw records. Derived semantic projections can be rebuilt independently.
