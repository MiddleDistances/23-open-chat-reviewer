#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"
[[ -f "$ENV_FILE" ]] || {
    printf 'Writer configuration is missing: %s\n' "$ENV_FILE" >&2
    exit 78
}

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
if [[ "${CHATREVIEW_NODE_ROLE:-}" != "writer" ]]; then
    printf 'Refusing to install a writer agent without CHATREVIEW_NODE_ROLE=writer\n' >&2
    exit 78
fi
command -v flock >/dev/null 2>&1 || {
    printf 'flock is required; install it with Homebrew before continuing\n' >&2
    exit 78
}

LABEL="org.openchatreviewer.writer"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p -- "$HOME/Library/LaunchAgents" "$REPO_ROOT/.chatreview/logs"
sed "s|@REPO_ROOT@|$REPO_ROOT|g" \
    "$REPO_ROOT/deploy/launchd/$LABEL.plist.in" > "$TARGET"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
launchctl print "gui/$(id -u)/$LABEL"
