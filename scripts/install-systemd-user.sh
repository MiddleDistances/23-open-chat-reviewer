#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WITH_WORKER=0
if [[ "${1:-}" == "--with-worker" ]]; then
    WITH_WORKER=1
elif [[ -n "${1:-}" ]]; then
    printf 'Usage: %s [--with-worker]\n' "$0" >&2
    exit 64
fi
mkdir -p -- "$UNIT_DIR"

names=(open-chat-reviewer-web)
if [[ "$WITH_WORKER" == "1" ]]; then
    names+=(open-chat-reviewer-worker)
fi
for name in "${names[@]}"; do
    sed "s|@REPO_ROOT@|$REPO_ROOT|g" \
        "$REPO_ROOT/deploy/systemd/$name.service.in" > "$UNIT_DIR/$name.service"
done

systemctl --user daemon-reload
units=(open-chat-reviewer-web.service)
if [[ "$WITH_WORKER" == "1" ]]; then
    units+=(open-chat-reviewer-worker.service)
fi
systemctl --user enable --now "${units[@]}"
systemctl --user status "${units[@]}" --no-pager
