#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p -- "$UNIT_DIR"

for name in open-chat-reviewer-worker open-chat-reviewer-web; do
    sed "s|@REPO_ROOT@|$REPO_ROOT|g" \
        "$REPO_ROOT/deploy/systemd/$name.service.in" > "$UNIT_DIR/$name.service"
done

systemctl --user daemon-reload
systemctl --user enable --now open-chat-reviewer-worker.service open-chat-reviewer-web.service
systemctl --user status open-chat-reviewer-worker.service open-chat-reviewer-web.service --no-pager
