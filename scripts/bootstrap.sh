#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
cd -- "$REPO_ROOT"

command -v uv >/dev/null 2>&1 || {
    printf 'uv is required: https://docs.astral.sh/uv/\n' >&2
    exit 78
}
command -v docker >/dev/null 2>&1 || {
    printf 'Docker with Compose is required for the bundled database\n' >&2
    exit 78
}

uv sync
if [[ ! -f .chatreview/archive.env ]]; then
    .venv/bin/open-chat-reviewer init --network "${CHATREVIEW_INIT_NETWORK:-auto}"
fi

set -a
# shellcheck disable=SC1091
source .chatreview/archive.env
set +a

docker compose up -d db
.venv/bin/open-chat-reviewer db migrate

if command -v bun >/dev/null 2>&1; then
    .venv/bin/open-chat-reviewer build-web
else
    printf 'Bun was not found; the CLI is ready, but build the UI later with bun.\n'
fi

if [[ "${CHATREVIEW_WEB_TAILSCALE_ONLY:-0}" == "1" ]]; then
    web_host="$(tailscale ip -4)"
else
    web_host="${CHATREVIEW_WEB_HOST:-127.0.0.1}"
fi
printf 'Bootstrap complete. Web URL after launch: http://%s:%s\n' \
    "$web_host" "${CHATREVIEW_WEB_PORT:-8765}"
printf 'Start the web service, open Setup, and choose the history range before the first import.\n'
