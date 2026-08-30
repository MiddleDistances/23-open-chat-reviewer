#!/usr/bin/env bash
# Restore an explicit pg_dump archive after confirming the target database name.

set -Eeuo pipefail
umask 077

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"
BACKUP_FILE="${1:-}"
CONFIRMED_NAME="${2:-}"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
: "${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required}"
if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
    printf 'Usage: %s /path/to/backup.dump exact_database_name\n' "$0" >&2
    exit 64
fi
command -v psql >/dev/null 2>&1 && command -v pg_restore >/dev/null 2>&1 || {
    printf 'psql and pg_restore are required\n' >&2
    exit 78
}

ACTUAL_NAME="$(psql "$CHATREVIEW_DATABASE_URL" -AtX -c 'SELECT current_database()')"
if [[ -z "$CONFIRMED_NAME" || "$CONFIRMED_NAME" != "$ACTUAL_NAME" ]]; then
    printf 'Restore replaces data in `%s`. Re-run with that exact database name as argument 2.\n' "$ACTUAL_NAME" >&2
    exit 64
fi

pg_restore --clean --if-exists --no-owner --no-privileges --dbname="$CHATREVIEW_DATABASE_URL" "$BACKUP_FILE"
printf 'Restore complete for database: %s\n' "$ACTUAL_NAME"
