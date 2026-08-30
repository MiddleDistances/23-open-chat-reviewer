#!/usr/bin/env bash
# Disconnect automatic services while deliberately preserving the archive and checkout.

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now open-chat-reviewer-web.service open-chat-reviewer-worker.service open-chat-reviewer-writer.service 2>/dev/null || true
    UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    rm -f -- "$UNIT_DIR/open-chat-reviewer-web.service" "$UNIT_DIR/open-chat-reviewer-worker.service" "$UNIT_DIR/open-chat-reviewer-writer.service"
    systemctl --user daemon-reload
elif [[ "$(uname -s)" == "Darwin" ]]; then
    for label in org.openchatreviewer.web org.openchatreviewer.worker org.openchatreviewer.writer; do
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
        rm -f -- "$HOME/Library/LaunchAgents/$label.plist"
    done
fi

printf 'Automatic services were removed.\n'
printf 'Your database, .chatreview runtime data, source chats, and checkout were preserved.\n'
printf 'Use scripts/backup.sh before manually deleting any preserved data.\n'
