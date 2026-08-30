#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
LABEL="org.openchatreviewer.worker"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p -- "$HOME/Library/LaunchAgents" "$REPO_ROOT/.chatreview/logs"
sed "s|@REPO_ROOT@|$REPO_ROOT|g" \
    "$REPO_ROOT/deploy/launchd/$LABEL.plist.in" > "$TARGET"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$TARGET"
launchctl enable "gui/$(id -u)/$LABEL"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
launchctl print "gui/$(id -u)/$LABEL"
