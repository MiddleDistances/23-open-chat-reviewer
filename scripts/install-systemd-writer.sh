#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
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
    printf 'Refusing to install a writer timer without CHATREVIEW_NODE_ROLE=writer\n' >&2
    exit 78
fi

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p -- "$UNIT_DIR"
for unit in open-chat-reviewer-writer.service open-chat-reviewer-writer.timer; do
    sed "s|@REPO_ROOT@|$REPO_ROOT|g" \
        "$REPO_ROOT/deploy/systemd/$unit.in" > "$UNIT_DIR/$unit"
done

systemctl --user daemon-reload
systemctl --user enable --now open-chat-reviewer-writer.timer
systemctl --user start open-chat-reviewer-writer.service
systemctl --user status open-chat-reviewer-writer.timer --no-pager
