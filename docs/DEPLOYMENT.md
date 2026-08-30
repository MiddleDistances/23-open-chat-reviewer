# Deployment

Open Chat Reviewer is designed for one trusted user or a small trusted team on a private
Tailscale network. PostgreSQL is authoritative; `.chatreview/` holds only local
configuration, reports, locks, and logs. The preferred multi-machine topology is covered
in [Tailscale central archive and remote writers](TAILSCALE_MULTI_MACHINE.md).

## Bundled database

`compose.yaml` starts PostgreSQL 17 with pgvector on the address selected by `init` and a
named volume. Automatic initialization prefers an active Tailscale IPv4 address and
generates a random database password; it falls back to loopback when Tailscale is absent:

```bash
docker compose up -d db
source .chatreview/archive.env
uv run open-chat-reviewer db migrate
uv run open-chat-reviewer db doctor
```

Legacy or hand-written configuration falls back to the local `chatreview` password only
for compatibility. Never use that fallback beyond loopback. Back up the named volume
through PostgreSQL tools, and practice restore before relying on the archive.

## Web process

```bash
scripts/chatreview-web.sh
```

The script binds to Tailscale when generated configuration contains
`CHATREVIEW_WEB_TAILSCALE_ONLY=1`; an explicit loopback installation binds to
`127.0.0.1:8765`. There is no application authentication layer, so never bind directly to
a public interface. Use least-privilege Tailscale grants and one database login per writer.

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
