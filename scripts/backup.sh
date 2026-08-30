#!/usr/bin/env bash
# Create a restorable PostgreSQL backup without copying source chat directories.

set -Eeuo pipefail
umask 077

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"
BACKUP_DIR="${CHATREVIEW_BACKUP_DIR:-$REPO_ROOT/.chatreview/backups}"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
: "${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required}"
command -v pg_dump >/dev/null 2>&1 || {
    printf 'pg_dump is required (install the PostgreSQL client tools)\n' >&2
    exit 78
}

mkdir -p -- "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_DIR/open-chat-reviewer-$STAMP.dump"
pg_dump --format=custom --no-owner --no-privileges --file="$TARGET" "$CHATREVIEW_DATABASE_URL"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$TARGET" > "$TARGET.sha256"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$TARGET" > "$TARGET.sha256"
fi
printf 'Backup complete: %s\n' "$TARGET"
