#!/usr/bin/env bash
# Add the "Token cost" tab to this checkout and rebuild the interface.
#
# Patches two upstream files (src/chatreview/api.py and web/src/App.tsx),
# twenty lines in total, keeping the originals alongside as .orig. Idempotent:
# re-run it after any update that reverts those files.
#
#   bash contrib/token-cost/install-token-tab.sh

set -Eeuo pipefail

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mxx  %s\033[0m\n' "$*" >&2; exit 1; }

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="${CHATREVIEW_REPO:-$(cd -- "$HERE/../.." && pwd -P)}"

[[ -f "$REPO/pyproject.toml" ]]           || die "$REPO does not look like the repository root"
[[ -f "$HERE/apply_panel_patch.py" ]]     || die "apply_panel_patch.py must sit beside this script"
[[ -f "$REPO/src/chatreview/token_panel.py" ]] || die "src/chatreview/token_panel.py is missing"
command -v bun >/dev/null 2>&1 || { export BUN_INSTALL="$HOME/.bun"; export PATH="$BUN_INSTALL/bin:$PATH"; }
command -v bun >/dev/null 2>&1 || die "bun not found; it is needed to rebuild the interface"

say "Applying the patch"
python3 "$HERE/apply_panel_patch.py" --repo "$REPO"

say "Rebuilding the interface (this clears web/dist)"
cd "$REPO/web"
bun install --frozen-lockfile
bun run build
cd "$REPO"

say "Leaving a redirect for any old bookmark"
cat > "$REPO/web/dist/token-report.html" <<'REDIRECT'
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Token Spend</title>
<meta http-equiv="refresh" content="0; url=/token-cost">
<style>body{font:16px/1.6 system-ui,sans-serif;margin:0;padding:48px;color:#171A1F;background:#F6F7F9}
a{color:#0B5299}@media(prefers-color-scheme:dark){body{background:#14161B;color:#E6E9EE}a{color:#6BAEEC}}</style>
</head><body><p>The report lives in the app now. Redirecting to <a href="/token-cost">Token cost</a>.</p></body></html>
REDIRECT

# Retire the standalone variants if they were installed previously.
for unit in token-live.service token-report.timer; do
    if systemctl --user is-enabled "$unit" >/dev/null 2>&1; then
        say "Retiring $unit"
        systemctl --user disable --now "$unit" || true
    fi
done

if systemctl --user is-active open-chat-reviewer-web.service >/dev/null 2>&1; then
    say "Restarting the web service"
    systemctl --user restart open-chat-reviewer-web.service
    ok=0
    for _ in $(seq 1 45); do
        curl -fsS --max-time 5 "http://127.0.0.1:8765/token-report" -o /dev/null 2>/dev/null && { ok=1; break; }
        sleep 2
    done
    [[ "$ok" == "1" ]] && printf '\n\033[1;32mDone.\033[0m  Sidebar > Work archive > Token cost\n' \
                       || printf '\n\033[1;33mNot answering yet.\033[0m journalctl --user -u open-chat-reviewer-web -n 40\n'
else
    printf '\n\033[1;32mPatched.\033[0m Start the web service, then open /token-cost\n'
fi

cat <<EOF

  Tab        http://127.0.0.1:8765/token-cost
  Re-apply   bash contrib/token-cost/install-token-tab.sh
  Revert     git checkout -- src/chatreview/api.py web/src/App.tsx && (cd web && bun run build)

EOF
