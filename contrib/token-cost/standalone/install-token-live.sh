#!/usr/bin/env bash
# Replace the scheduled static token report with a live one.
#
# Installs a small read-only HTTP service on 127.0.0.1:8766 that rebuilds the
# report on every page load. Usage figures are extracted once into a private
# PostgreSQL schema (token_report) and topped up incrementally, so refreshes
# return in milliseconds rather than re-reading every payload.
#
# Nothing in the upstream repository or its schema is modified.
#
#   bash install-token-live.sh

set -Eeuo pipefail

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mxx  %s\033[0m\n' "$*" >&2; exit 1; }

REPO="$HOME/open-chat-reviewer"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PORT="${TOKEN_LIVE_PORT:-8766}"

[[ -d "$REPO" ]]                          || die "Repository not found at $REPO"
[[ -f "$HOME/token-report.py" ]]          || die "token-report.py must be in $HOME (it supplies the renderer)"
[[ -f "$HOME/token-live.py" ]]            || die "token-live.py must be in $HOME"
[[ -x "$REPO/.venv/bin/python" ]]         || die "Virtualenv missing. Run 'uv sync' in $REPO first."
[[ -f "$REPO/.chatreview/archive.env" ]]  || die "archive.env not found."
systemctl --user show-environment >/dev/null 2>&1 || die "systemd user session unavailable."

# ------------------------------------------- 1. retire the scheduled version
if systemctl --user is-enabled token-report.timer >/dev/null 2>&1; then
    say "Retiring the six-hourly static report"
    systemctl --user disable --now token-report.timer || true
fi

# ---------------------------------------------------------- 2. the wrapper
say "Writing $HOME/token-live.sh"
cat > "$HOME/token-live.sh" <<WRAP
#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
REPO="\$HOME/open-chat-reviewer"
ENV_FILE="\${CHATREVIEW_ENV_FILE:-\$REPO/.chatreview/archive.env}"
if [[ -f "\$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "\$ENV_FILE"
    set +a
fi
: "\${CHATREVIEW_DATABASE_URL:?CHATREVIEW_DATABASE_URL is required}"
cd "\$REPO"
exec "\$REPO/.venv/bin/python" "\$HOME/token-live.py" --host 127.0.0.1 --port ${PORT}
WRAP
chmod 700 "$HOME/token-live.sh"

# ------------------------------------------------------------- 3. the unit
say "Installing the service"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/token-live.service" <<UNIT
[Unit]
Description=Live token cost report for the Open Chat Reviewer archive
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/open-chat-reviewer
ExecStart=%h/token-live.sh
Restart=on-failure
RestartSec=10
NoNewPrivileges=true

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now token-live.service

# ------------------------------- 4. keep the old bookmark working
say "Pointing the old URL at the live one"
mkdir -p "$REPO/web/dist"
cat > "$REPO/web/dist/token-report.html" <<REDIRECT
<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Token Spend</title>
<meta http-equiv="refresh" content="0; url=http://127.0.0.1:${PORT}/">
<style>body{font:16px/1.6 system-ui,sans-serif;margin:0;padding:48px;color:#171A1F;background:#F6F7F9}
a{color:#0B5299}@media(prefers-color-scheme:dark){body{background:#14161B;color:#E6E9EE}a{color:#6BAEEC}}</style>
</head><body><p>The token report is now live. Redirecting to
<a href="http://127.0.0.1:${PORT}/">127.0.0.1:${PORT}</a>.</p></body></html>
REDIRECT

# ---------------------------------------------------------------- 5. check
say "Waiting for the first build (it backfills the table once, so allow a minute)"
ok=0
for _ in $(seq 1 60); do
    if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/" -o /dev/null 2>/dev/null; then ok=1; break; fi
    sleep 2
done

if [[ "$ok" == "1" ]]; then
    printf '\n\033[1;32mLive.\033[0m  http://127.0.0.1:%s\n' "$PORT"
else
    printf '\n\033[1;33mNot answering yet.\033[0m Check: journalctl --user -u token-live -n 40\n'
fi

cat <<EOF

  View        http://127.0.0.1:${PORT}
  Old link    http://127.0.0.1:8765/token-report.html  (redirects here)
  Logs        journalctl --user -u token-live -f
  Restart     systemctl --user restart token-live
  Stop        systemctl --user disable --now token-live

Every refresh tops up the usage table and re-aggregates, so the page always
reflects whatever the worker has imported. Only new events are read, so it
stays fast as the archive grows.
EOF
