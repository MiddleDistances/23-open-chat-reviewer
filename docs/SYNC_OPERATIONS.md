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

Useful controls:

```bash
uv run open-chat-reviewer inventory --no-git
uv run open-chat-reviewer sync --provider codex --provider claude --workers 2
uv run open-chat-reviewer episodes --force
uv run open-chat-reviewer timesheets build --force
uv run open-chat-reviewer status
```

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

## Freshness contract

`sync` updates the raw and canonical archive. Episodes, semantic indexes, workload
snapshots, and resume cards are separate projections. `worker run` handles episodes,
timesheets, and optional summaries; semantic refreshes remain deliberate because model
downloads and GPU use can be substantial.

Always check:

```bash
uv run open-chat-reviewer status
```

Missing semantic indexes and an empty optional activity catalog are reported but do not
make the core archive unhealthy. Failed sources, partial revisions, or stale required
projections do.

## Recovery

1. Run `uv run open-chat-reviewer db doctor`.
2. Inspect the daily sync log and `uv run open-chat-reviewer status`.
3. Verify that source files are stable and readable; never edit them as recovery.
4. Re-run sync. Completed source offsets are reused.
5. Use `--force` only for a derived projection that must be rebuilt.

Back up PostgreSQL with normal `pg_dump`/restore tooling. The `.chatreview/` directory is
not a substitute for a database backup.
