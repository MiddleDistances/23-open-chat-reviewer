#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
WITH_WORKER=0
if [[ "${1:-}" == "--with-worker" ]]; then
  WITH_WORKER=1
elif [[ -n "${1:-}" ]]; then
  printf 'Usage: %s [--with-worker]\n' "$0" >&2
  exit 64
fi

mkdir -p -- "$HOME/Library/LaunchAgents" "$REPO_ROOT/.chatreview/logs"
labels=(org.openchatreviewer.web)
if [[ "$WITH_WORKER" == "1" ]]; then
  labels+=(org.openchatreviewer.worker)
fi
for label in "${labels[@]}"; do
  target="$HOME/Library/LaunchAgents/$label.plist"
  sed "s|@REPO_ROOT@|$REPO_ROOT|g" \
      "$REPO_ROOT/deploy/launchd/$label.plist.in" > "$target"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$target"
  launchctl enable "gui/$(id -u)/$label"
  launchctl kickstart -k "gui/$(id -u)/$label"
  launchctl print "gui/$(id -u)/$label"
done
