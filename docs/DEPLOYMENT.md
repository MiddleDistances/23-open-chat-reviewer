# Deployment

Open Chat Reviewer is designed for one trusted user or a small trusted team on a private
network. PostgreSQL is authoritative; `.chatreview/` holds only local configuration,
reports, locks, and logs.

## Bundled database

`compose.yaml` starts PostgreSQL 17 with pgvector on loopback port `54329` and a named
volume:

```bash
docker compose up -d db
source .chatreview/archive.env
uv run open-chat-reviewer db migrate
uv run open-chat-reviewer db doctor
```

Change the example password for any non-local deployment. Back up the named volume through
PostgreSQL tools, and practice restore before relying on the archive.

## Web process

```bash
scripts/chatreview-web.sh
```

The default bind is `127.0.0.1:8765`. To bind to your Tailscale address, set
`CHATREVIEW_WEB_TAILSCALE_ONLY=1`. There is no application authentication layer, so never
bind directly to a public interface. For shared use, put an authenticated TLS reverse
proxy in front and use a least-privilege database role.

## Background services

Linux user services:

```bash
scripts/install-systemd-user.sh
```

This installs and starts worker and web units under `~/.config/systemd/user`. Inspect them
with `systemctl --user status open-chat-reviewer-worker open-chat-reviewer-web`.

macOS worker:

```bash
brew install flock
scripts/install-launchd.sh
```

The LaunchAgent writes logs under `.chatreview/logs/`. Start the web process separately or
place it behind your preferred local service manager.

## External PostgreSQL

Set `CHATREVIEW_DATABASE_URL` to a PostgreSQL 17-compatible server with permission to
create the `vector` and `pg_trgm` extensions during initial migration. Use TLS and a
dedicated database/user. Database URLs belong only in `.chatreview/archive.env` or your
service manager's secret store.

## Upgrade

```bash
git pull --ff-only
uv sync --frozen
source .chatreview/archive.env
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer db migrate
cd web && bun install --frozen-lockfile && bun run build
```

Restart the worker and web process after validation. Read migration files before applying
them and back up PostgreSQL before any upgrade with material schema changes.
