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
