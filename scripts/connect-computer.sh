#!/usr/bin/env bash
# Install one source-only writer from a private invitation file.

set -Eeuo pipefail
umask 077

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
CONFIG_FILE="${1:-}"

if [[ -z "$CONFIG_FILE" || ! -f "$CONFIG_FILE" ]]; then
    printf 'Usage: %s /path/to/private-writer.env [writer install options]\n' "$0" >&2
    exit 64
fi
shift

command -v uv >/dev/null 2>&1 || {
    printf 'uv is required: https://docs.astral.sh/uv/\n' >&2
    exit 78
}
if [[ "$(uname -s)" == "Darwin" ]] && ! command -v flock >/dev/null 2>&1; then
    command -v brew >/dev/null 2>&1 || {
        printf 'Install Homebrew, then run: brew install flock\n' >&2
        exit 78
    }
    brew install flock
fi

cd -- "$REPO_ROOT"
uv sync
exec .venv/bin/open-chat-reviewer writer install "$CONFIG_FILE" "$@"
