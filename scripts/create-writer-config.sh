#!/usr/bin/env bash
# Create a least-privilege PostgreSQL login and private config for one writer machine.

set -Eeuo pipefail
umask 077

SCRIPT_PATH="${BASH_SOURCE[0]}"
if command -v readlink >/dev/null 2>&1; then
    SCRIPT_PATH="$(readlink -f -- "$SCRIPT_PATH")"
fi
REPO_ROOT="$(cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd -P)"
cd -- "$REPO_ROOT"

ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

writer_slug="${1:-}"
if [[ ! "$writer_slug" =~ ^[a-z0-9][a-z0-9-]{0,30}$ ]]; then
    printf 'Usage: %s <writer-name> (lowercase letters, digits, and hyphens)\n' "$0" >&2
    exit 64
fi
: "${CHATREVIEW_PUBLIC_DATABASE_HOST:?Run central init with Tailscale before creating writers}"
: "${CHATREVIEW_DB_PORT:=54329}"

command -v docker >/dev/null 2>&1 || {
    printf 'Docker with Compose is required to provision a bundled-database writer role\n' >&2
    exit 78
}
command -v openssl >/dev/null 2>&1 || {
    printf 'openssl is required to generate a writer password\n' >&2
    exit 78
}
[[ -x "$REPO_ROOT/.venv/bin/python" ]] || {
    printf 'Run uv sync before creating writer configuration\n' >&2
    exit 78
}

writer_name="chatreview_writer_${writer_slug//-/_}"
writer_password="$(openssl rand -hex 24)"
writer_machine_id="$("$REPO_ROOT/.venv/bin/python" -c 'from uuid import uuid4; print(uuid4())')"
writer_dir="$REPO_ROOT/.chatreview/writers"
writer_file="$writer_dir/$writer_slug.env"
if [[ -e "$writer_file" ]]; then
    printf 'Refusing to overwrite existing writer configuration: %s\n' "$writer_file" >&2
    exit 73
fi

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U chatreview -d chatreview \
    -v writer_name="$writer_name" -v writer_password="$writer_password" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'writer_name', :'writer_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'writer_name') \gexec
SELECT format('ALTER ROLE %I PASSWORD %L', :'writer_name', :'writer_password') \gexec
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', current_database(), :'writer_name') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'writer_name') \gexec
SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO %I',
    :'writer_name'
) \gexec
SELECT format(
    'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I',
    :'writer_name'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO %I',
    :'writer_name'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I',
    :'writer_name'
) \gexec
SQL

writer_url="postgresql://${writer_name}:${writer_password}@${CHATREVIEW_PUBLIC_DATABASE_HOST}:${CHATREVIEW_DB_PORT}/chatreview"
mkdir -p -- "$writer_dir"
{
    printf 'export CHATREVIEW_DATABASE_URL=%q\n' "$writer_url"
    printf 'export CHATREVIEW_MACHINE_ID=%q\n' "$writer_machine_id"
    printf 'export CHATREVIEW_MACHINE_NAME=%q\n' "$writer_slug"
    printf 'export CHATREVIEW_NODE_ROLE=writer\n'
    printf 'export CHATREVIEW_CODEX_ROOT="$HOME/.codex"\n'
    printf 'export CHATREVIEW_CLAUDE_ROOT="$HOME/.claude"\n'
    printf 'export CHATREVIEW_GEMINI_ROOT="$HOME/.gemini"\n'
    printf 'export CHATREVIEW_GIT_ROOT="$HOME/Projects"\n'
    printf 'export CHATREVIEW_ENABLE_GIT=1\n'
    printf 'export CHATREVIEW_ENABLE_SUMMARIES=0\n'
} > "$writer_file"
chmod 600 "$writer_file"

printf 'Created private writer configuration: %s\n' "$writer_file"
printf 'Copy it securely to %s, then run `uv run open-chat-reviewer writer install <file>`.\n' \
    "$writer_slug"
printf 'Delete the transfer copy after installation; migrations and derived workers stay central.\n'
