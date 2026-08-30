#!/usr/bin/env bash
# Fast-forward a clean checkout, refresh dependencies, migrate, and restart known services.

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
cd -- "$REPO_ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
    printf 'Update stopped: the checkout has local changes. Commit or stash them first.\n' >&2
    exit 73
fi
git pull --ff-only
sync_args=()
if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import importlib.util, sys; sys.exit(importlib.util.find_spec("mcp") is None)'; then
    sync_args+=(--extra mcp)
fi
if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import importlib.util, sys; sys.exit(importlib.util.find_spec("sentence_transformers") is None)'; then
    sync_args+=(--extra semantic)
fi
uv sync "${sync_args[@]}"

set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.chatreview/archive.env"
set +a
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer db migrate
if command -v bun >/dev/null 2>&1; then
    uv run open-chat-reviewer build-web
elif command -v npm >/dev/null 2>&1; then
    npm --prefix web run build
fi

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user try-restart open-chat-reviewer-web.service open-chat-reviewer-worker.service 2>/dev/null || true
elif [[ "$(uname -s)" == "Darwin" ]]; then
    launchctl kickstart -k "gui/$(id -u)/org.openchatreviewer.web" 2>/dev/null || true
fi
printf 'Open Chat Reviewer is up to date.\n'
