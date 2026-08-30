#!/usr/bin/env bash
# Repeatable PostgreSQL archive sync for Open Chat Reviewer source machines.
#
# The Python command owns source-level resumability and PostgreSQL transactions.
# This wrapper owns deployment concerns: configuration loading, process locking,
# preflight checks, and durable operational logs.

set -Eeuo pipefail
umask 027

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
cd -- "$REPO_ROOT"

ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

# A GUI setup build may deliberately override the persisted retention policy for
# this one run. The override contains only the enum value preserve/redact, never
# credentials, and is not written back to archive.env.
if [[ -n "${CHATREVIEW_RAW_REASONING_RETENTION_OVERRIDE:-}" ]]; then
    export CHATREVIEW_RAW_REASONING_RETENTION="$CHATREVIEW_RAW_REASONING_RETENTION_OVERRIDE"
fi

: "${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required (set it or provide CHATREVIEW_ENV_FILE)}"
: "${CHATREVIEW_MACHINE_ID:?CHATREVIEW_MACHINE_ID is required (set it or provide CHATREVIEW_ENV_FILE)}"

CLI="${CHATREVIEW_SYNC_CLI:-$REPO_ROOT/.venv/bin/open-chat-reviewer}"
DATA_DIR="${CHATREVIEW_DATA_DIR:-$REPO_ROOT/.chatreview}"
LOCK_FILE="${CHATREVIEW_SYNC_LOCK_FILE:-$DATA_DIR/sync.lock}"
LOG_DIR="${CHATREVIEW_SYNC_LOG_DIR:-$DATA_DIR/logs}"
LOG_FILE="${CHATREVIEW_SYNC_LOG_FILE:-$LOG_DIR/sync-$(date -u +%Y%m%d).log}"
MIGRATE="${CHATREVIEW_SYNC_MIGRATE:-0}"
WORKERS="${CHATREVIEW_SYNC_WORKERS:-1}"
BATCH_LINES="${CHATREVIEW_SYNC_BATCH_LINES:-1000}"

if [[ ! -x "$CLI" ]]; then
    printf 'Open Chat Reviewer CLI is not executable: %s\n' "$CLI" >&2
    exit 78
fi
if ! command -v flock >/dev/null 2>&1; then
    printf 'flock is required for single-run protection\n' >&2
    exit 78
fi

CODEX_ROOT="${CHATREVIEW_CODEX_ROOT:-$HOME/.codex}"
CLAUDE_ROOT="${CHATREVIEW_CLAUDE_ROOT:-$HOME/.claude}"
GEMINI_ROOT="${CHATREVIEW_GEMINI_ROOT:-$HOME/.gemini}"
GIT_ROOT="${CHATREVIEW_GIT_ROOT:-$HOME/Projects}"
if [[ ! -d "$CODEX_ROOT/sessions" && ! -d "$CLAUDE_ROOT/projects" \
    && ! -d "$GEMINI_ROOT/tmp" && ! -f "$CODEX_ROOT/history.jsonl" \
    && ! -f "$CLAUDE_ROOT/history.jsonl" && ! -d "$GIT_ROOT" ]]; then
    printf 'No Codex, Claude, Gemini, or Git source roots were found; refusing an empty sync\n' >&2
    exit 78
fi

case "$MIGRATE" in
    0|1) ;;
    *)
        printf 'CHATREVIEW_SYNC_MIGRATE must be 0 or 1\n' >&2
        exit 78
        ;;
esac

case "$WORKERS" in
    ''|*[!0-9]*|0)
        printf 'CHATREVIEW_SYNC_WORKERS must be a positive integer\n' >&2
        exit 78
        ;;
esac

case "$BATCH_LINES" in
    ''|*[!0-9]*|0)
        printf 'CHATREVIEW_SYNC_BATCH_LINES must be a positive integer\n' >&2
        exit 78
        ;;
esac

SYNC_ARGS=("$@")
has_workers=0
has_batch_lines=0
for argument in "$@"; do
    case "$argument" in
        --workers|--workers=*) has_workers=1 ;;
        --batch-lines|--batch-lines=*) has_batch_lines=1 ;;
    esac
done
if [[ "$has_workers" == 0 ]]; then
    SYNC_ARGS+=(--workers "$WORKERS")
fi
if [[ "$has_batch_lines" == 0 ]]; then
    SYNC_ARGS+=(--batch-lines "$BATCH_LINES")
fi

mkdir -p -- "$LOG_DIR" "$(dirname -- "$LOCK_FILE")" "$(dirname -- "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
finish() {
    local status=$?
    printf 'finished_at=%s exit_status=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$status"
}
trap finish EXIT

if [[ "${CHATREVIEW_SYNC_LOCK_INHERITED:-0}" == 1 ]]; then
    printf 'Using the caller-held Open Chat Reviewer lock=%s\n' "$LOCK_FILE"
else
    # macOS ships Bash 3.2, which does not support `exec {name}>file` dynamic
    # descriptors. Reserve descriptor 9 so the wrapper remains portable while
    # this shell holds the lock for the full sync.
    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
        printf 'Another Open Chat Reviewer sync is already running; lock=%s\n' "$LOCK_FILE"
        exit 75
    fi
fi

printf 'started_at=%s\n' "$started_at"
printf 'repo_root=%s\n' "$REPO_ROOT"
printf 'environment_file=%s\n' "$ENV_FILE"
printf 'lock_file=%s\n' "$LOCK_FILE"
printf 'log_file=%s\n' "$LOG_FILE"
printf 'command='
printf '%q ' "$CLI" sync "${SYNC_ARGS[@]}"
printf '\n'

if [[ "$MIGRATE" == 1 ]]; then
    printf 'Applying ordered database migrations before sync\n'
    "$CLI" db migrate
fi

printf 'Running PostgreSQL preflight\n'
"$CLI" db doctor

printf 'Running resumable source sync\n'
"$CLI" sync "${SYNC_ARGS[@]}"
