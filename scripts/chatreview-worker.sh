#!/usr/bin/env bash

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

: "${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required}"
: "${CHATREVIEW_MACHINE_ID:?CHATREVIEW_MACHINE_ID is required}"

CLI="${CHATREVIEW_WORKER_CLI:-$REPO_ROOT/.venv/bin/open-chat-reviewer}"
INTERVAL="${CHATREVIEW_SYNC_INTERVAL:-21600}"
WORKERS="${CHATREVIEW_SYNC_WORKERS:-1}"

exec "$CLI" worker run --interval "$INTERVAL" --sync-workers "$WORKERS" "$@"
