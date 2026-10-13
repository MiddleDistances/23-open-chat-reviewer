#!/usr/bin/env bash
# Run the CLI from the project root with its explicitly selected configuration.
set -Eeuo pipefail
umask 027

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENV_FILE="${CHATREVIEW_ENV_FILE:-$REPO_ROOT/.chatreview/archive.env}"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # The selected file is trusted, machine-local shell configuration.
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
elif [[ -n "${CHATREVIEW_ENV_FILE:-}" ]]; then
    printf '%s\n' 'CHATREVIEW_ENV_FILE does not name an existing configuration file.' >&2
    exit 78
fi

if [[ -z "${CHATREVIEW_DATABASE_URL:-}" || -z "${CHATREVIEW_MACHINE_ID:-}" ]]; then
    printf '%s\n' 'Configure CHATREVIEW_DATABASE_URL and CHATREVIEW_MACHINE_ID, or select a trusted file with CHATREVIEW_ENV_FILE.' >&2
    exit 78
fi

cd -- "$REPO_ROOT"
exec uv run open-chat-reviewer "$@"
