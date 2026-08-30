#!/usr/bin/env bash

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

: "${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required; run scripts/install.sh first}"

exec "$REPO_ROOT/.venv/bin/open-chat-reviewer-mcp" "$@"
