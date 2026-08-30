#!/usr/bin/env bash
# Prepare the central archive and start the web UI without importing chat history yet.

set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"

"$REPO_ROOT/scripts/bootstrap.sh"

case "$(uname -s)" in
    Linux)
        if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
            "$REPO_ROOT/scripts/install-systemd-user.sh"
        else
            printf 'Automatic startup is unavailable. Run: %s/scripts/chatreview-web.sh\n' "$REPO_ROOT"
        fi
        ;;
    Darwin)
        "$REPO_ROOT/scripts/install-launchd.sh"
        ;;
    *)
        printf 'Automatic startup is unavailable. Run: %s/scripts/chatreview-web.sh\n' "$REPO_ROOT"
        ;;
esac

printf '\nOpen the URL above and use Setup. No chat history was imported automatically.\n'
