#!/usr/bin/env bash
# Launch Open Chat Reviewer on loopback or an explicitly selected private interface.

set -Eeuo pipefail
umask 027

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

: "${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required (set it or provide CHATREVIEW_ENV_FILE)}"
: "${CHATREVIEW_MACHINE_ID:?CHATREVIEW_MACHINE_ID is required (set it or provide CHATREVIEW_ENV_FILE)}"

CLI="${CHATREVIEW_WEB_CLI:-$REPO_ROOT/.venv/bin/open-chat-reviewer}"
DATA_DIR="${CHATREVIEW_DATA_DIR:-$REPO_ROOT/.chatreview}"
HOST="${CHATREVIEW_WEB_HOST:-127.0.0.1}"
PORT="${CHATREVIEW_WEB_PORT:-8765}"

if [[ "${CHATREVIEW_WEB_TAILSCALE_ONLY:-0}" == "1" ]]; then
    if ! command -v tailscale >/dev/null 2>&1; then
        printf 'tailscale is required for a tailnet-only web bind\n' >&2
        exit 78
    fi
    HOST="$(tailscale ip -4)"
    if [[ -z "$HOST" || "$HOST" == *$'\n'* ]]; then
        printf 'Expected exactly one active Tailscale IPv4 address\n' >&2
        exit 75
    fi
fi

if [[ ! -x "$CLI" ]]; then
    printf 'Open Chat Reviewer CLI is not executable: %s\n' "$CLI" >&2
    exit 78
fi

exec "$CLI" serve --data-dir "$DATA_DIR" --host "$HOST" --port "$PORT" --no-reload
