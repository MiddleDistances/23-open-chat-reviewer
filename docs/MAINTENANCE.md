# Backup, update, restore, and remove

All commands are run from the Open Chat Reviewer checkout. They load the ignored
`.chatreview/archive.env` file and do not print the database password.

## Backup

```bash
scripts/backup.sh
```

This writes a compressed PostgreSQL dump and checksum under
`.chatreview/backups/`. Copy that dump to another protected disk. Source chat
folders are read-only inputs and are not duplicated by this backup.

## Update

```bash
scripts/update.sh
```

The updater refuses a dirty Git checkout, fast-forwards the current branch,
refreshes dependencies, applies database migrations, rebuilds the UI, and restarts
an installed web service. Optional MCP and semantic dependencies remain installed
when they were already present.

## Restore

Restore is destructive. Stop active sync workers, then provide both the exact dump
path and the database name printed by PostgreSQL:

```bash
scripts/restore.sh .chatreview/backups/open-chat-reviewer-TIMESTAMP.dump chatreview
```

The second argument is a deliberate guard against restoring into the wrong database.

## Remove automatic services

```bash
scripts/uninstall.sh
```

Uninstall removes only automatic service registrations. It preserves PostgreSQL,
the `.chatreview/` directory, the checkout, and every source chat. Back up first,
then delete preserved data manually only when you are certain it is no longer needed.

## Preserve history while compacting timesheet evidence

Use the environment file actually selected by the running web and worker services.
A database name alone does not identify a cluster. Storage maintenance reports the
PostgreSQL system identifier, database OID, server port, schema, and migration history;
it never prints the database URL. Explicit `--env-file` takes precedence over the shell.
A selected file must exist and define `CHATREVIEW_DATABASE_URL`; missing settings never
fall back to a different database from the shell environment.

```bash
uv run open-chat-reviewer storage run audit --env-file /path/to/live.env
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer db migrate
uv run open-chat-reviewer storage run backfill --env-file /path/to/live.env \
  --apply --target <target-from-audit> --batch-size 200 --workers 4
uv run open-chat-reviewer storage run verify --env-file /path/to/live.env
```

The doctor and migration commands use `CHATREVIEW_DATABASE_URL`; load the same trusted
live environment first. Without `--apply`, maintenance operations only report. Backfill
commits bounded batches in up to four disjoint interval ranges, retains all legacy rows,
and resumes by skipping certified
intervals. It validates counts and complete event/episode membership, including null
references. Shared sets are immutable once referenced. Changes to legacy rows or interval
membership invalidate the corresponding certificate. A mismatch aborts the batch.

Deploy shared-evidence readers and writers together before backfill. The effective
evidence view supports both predecessor representations without counting both copies.
Every snapshot, cutoff, interval, artifact occurrence, encrypted payload and export
reference is retained. Neither the calculation algorithm nor source retention changes.

Before reclamation, verify a restorable backup, disk/WAL/archive headroom, and stop every
writer plus the web service for the maintenance window. Require zero uncertified intervals
and zero invalid sets. Then run:

```bash
uv run open-chat-reviewer storage run reclaim --env-file /path/to/live.env \
  --apply --target <target-from-audit>
```

Reclamation locks the proof inputs, rechecks completeness, and truncates only the legacy
`work_interval_evidence` table. It retains the empty table with a trigger that rejects old
writers. Restore service only after read/search/calendar/export checks. After reclamation,
rollback requires a shared-evidence-compatible release or the verified backup; an older
binary cannot safely read all historical evidence.

Migration 0023 retires the unused contents trigram index after a complete deployed-query
review; the index is no longer automatically rebuilt. Keep full-text and artifact substring
indexes. Audit and compact other relations only when measurements demonstrate waste;
allocated bytes and estimated dead-row counts alone do not establish reclaimable bytes.
