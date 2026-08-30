# Tailscale central archive and remote writers

Open Chat Reviewer is designed to collect read-only chat and Git evidence from several
computers into one PostgreSQL archive. The recommended deployment is a central node and
one writer configuration per source machine, all connected through a private Tailscale
network (a tailnet).

```text
Codex / Claude / Gemini / Git files          trusted browser
             |                                    |
      remote writer nodes                   TCP 8765
             |                                    |
             +---------- TCP 54329 ---------------+
                                  |
                         central Tailscale node
                         PostgreSQL + web + worker
```

Writers never modify or copy the source archives. They parse their local files and write
raw, hash-addressed records plus canonical projections to PostgreSQL. A stable, distinct
`CHATREVIEW_MACHINE_ID` keeps identical paths on different computers separate. The
central worker builds episodes, summaries, and workload snapshots across all machines.

## 1. Join the machines to one tailnet

Install Tailscale and sign in on the central node and every writer. Confirm each machine
can see the central node:

```bash
tailscale status
tailscale ping <central-machine-name>
```

Tailscale assigns stable private IP addresses and MagicDNS names. Open Chat Reviewer
binds directly to the central node's Tailscale IPv4 address; it does not use Tailscale
Serve or expose a public listener.

Use Tailscale grants to restrict database and UI access. Replace the example group member
and writer IPs with your tailnet values. Tag the unattended central node
`tag:chatreview-server`; keep personal laptops user-owned and identify their stable
Tailscale IPs with host aliases:

```json
{
  "groups": {
    "group:chatreview-viewers": ["you@example.com"]
  },
  "hosts": {
    "chatreview-laptop": "100.100.100.10",
    "chatreview-desktop": "100.100.100.11"
  },
  "tagOwners": {
    "tag:chatreview-server": ["autogroup:admin"]
  },
  "grants": [
    {
      "src": [
        "tag:chatreview-server",
        "chatreview-laptop",
        "chatreview-desktop"
      ],
      "dst": ["tag:chatreview-server"],
      "ip": ["tcp:54329"]
    },
    {
      "src": ["group:chatreview-viewers"],
      "dst": ["tag:chatreview-server"],
      "ip": ["tcp:8765"]
    }
  ]
}
```

Grants are deny-by-default and additive. Review the complete policy before saving it; an
existing broad rule can still grant access. Tailscale advises against tagging personal
user devices because applying a tag replaces their user identity. Tags are appropriate
for unattended service machines. See Tailscale's [grants syntax][grants], [device
tags][tags], and [MagicDNS][magicdns] documentation.

## 2. Bootstrap the central node

With Tailscale connected:

```bash
git clone https://github.com/MiddleDistances/23-open-chat-reviewer.git
cd 23-open-chat-reviewer
scripts/bootstrap.sh
scripts/chatreview-sync.sh
scripts/chatreview-web.sh
```

`init --network auto` is the bootstrap default. It prefers the active Tailscale interface,
generates a random 48-character PostgreSQL password, binds PostgreSQL only to that
Tailscale address, and binds the web process there as well. It records the MagicDNS name
for writer configuration. Force a local-only installation with:

```bash
CHATREVIEW_INIT_NETWORK=loopback scripts/bootstrap.sh
```

Verify the central services before adding writers:

```bash
source .chatreview/archive.env
docker compose ps
uv run open-chat-reviewer db doctor
ss -ltn '( sport = :54329 or sport = :8765 )'
```

Open `http://<central-machine-name>:8765` from another permitted tailnet device. The app
has no built-in authentication; the Tailscale grant is the access boundary. Never bind
either port to `0.0.0.0` or forward it from a public router.

The landing/setup screen on the central node is the operational front door. It should
show the central node's machine identity, database/web/worker health, discovered source
coverage, and the last completed raw/derived runs. Use it to choose the semantic date
scope and the independent reasoning controls (preserve encrypted raw, search readable
reasoning, embed readable reasoning) before starting an expensive semantic build.

## 3. Create one database login per writer

On the central node, after migrations are current:

```bash
scripts/create-writer-config.sh laptop
```

This creates or rotates a PostgreSQL role named `chatreview_writer_laptop`, grants only
the table and sequence rights needed for ingestion, and writes a mode-`0600` file at
`.chatreview/writers/laptop.env`. It does not print the database password.

The current database authorization boundary is table-level, not row-level: a compromised
writer credential can read the shared archive even though it cannot migrate the schema or
create database roles. Tailnet grants, device hygiene, and per-writer credential rotation
are therefore essential. Row-level writer isolation is intentionally not claimed.

Copy that file through a secure channel to
`23-open-chat-reviewer/.chatreview/archive.env` on the named writer. Delete any temporary
transfer copy. Never commit either file. If a writer is lost, remove its Tailscale device
and revoke its PostgreSQL role on the central node:

```sql
DROP ROLE chatreview_writer_laptop;
```

If the role still owns or is referenced by grants, run
`DROP OWNED BY chatreview_writer_laptop` first as the database owner. Creating a new
writer config for the same name rotates its password only when the old private config has
been removed intentionally.

## 4. Install and test a writer

The remote machine needs the repository, `uv`, Tailscale, and access to its local chat
directories. It does not need Docker or a local PostgreSQL server.

```bash
git clone https://github.com/MiddleDistances/23-open-chat-reviewer.git
cd 23-open-chat-reviewer
uv sync
mkdir -p .chatreview
# Securely place the generated file at .chatreview/archive.env, then:
chmod 600 .chatreview/archive.env
source .chatreview/archive.env
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer inventory
scripts/chatreview-sync.sh
```

Review and change `CHATREVIEW_CODEX_ROOT`, `CHATREVIEW_CLAUDE_ROOT`,
`CHATREVIEW_GEMINI_ROOT`, and `CHATREVIEW_GIT_ROOT` for that machine before its first
sync. Keep its generated `CHATREVIEW_MACHINE_ID` for the lifetime of that archive; do not
copy one writer's identity to another computer.

The writer's setup is local to that computer. Select its source roots and archive history
scope there; the central database will show this machine as a separate contributor. A
writer does not need a copy of another machine's chat files, and a new machine will not
be included merely because it joins the tailnet. The first-run preview should show
provider/file/byte counts and the effective earliest/latest source timestamps before
sync begins.

For a Linux writer, install the three-hour timer with randomized jitter:

```bash
scripts/install-systemd-writer.sh
systemctl --user list-timers open-chat-reviewer-writer.timer
journalctl --user -u open-chat-reviewer-writer.service
```

On macOS, install `flock` and the three-hour LaunchAgent:

```bash
brew install flock
scripts/install-launchd-writer.sh
launchctl print gui/$(id -u)/org.openchatreviewer.writer
```

The timer runs only `scripts/chatreview-sync.sh`. Writer nodes must not run `db migrate`,
the web app, or `worker run`. Schema changes and derived refreshes belong to the central
node. Stagger large first ingestions; normal incremental runs are resumable and use
machine-and-source-specific PostgreSQL advisory locks.

Keep the writer's `.chatreview/archive.env` private. It contains the central database
connection and the writer's machine identity. Do not commit it or copy it to another
machine. If a writer is reinstalled, restore its own ID only after confirming that the
local source roots represent the same computer; otherwise create a new writer identity.

## 5. Operate the central archive

Run the central worker after writer syncs. Its global worker lock ensures one projection
cycle builds episodes, workload snapshots, and optional summary cards at a time:

```bash
scripts/chatreview-worker.sh
uv run open-chat-reviewer status
```

The workload calendar then unions overlapping chat and Git intervals across the resolved
contributors and projects, while retaining each machine as source provenance.

The central PostgreSQL database stores the combined archive, not a filesystem mirror.
Chat raw payloads and canonical text are retained according to the configured retention
policy; episodes, semantic windows, embeddings, clusters, workload snapshots, and
summaries are derived layers. Git contributes repository/commit metadata, messages,
parents, timestamps, changed paths/status, and provenance—not Git blobs, patches, or
full checkout contents. Read [Setup, scope, and storage](SETUP_AND_STORAGE.md) before
changing raw-reasoning retention or semantic inclusion policy.

After writer syncs, check the central status page/command. A successful writer sync can
still leave episodes, timesheets, semantic runs, or resume cards stale until the central
worker or the deliberate semantic refresh completes. Semantic map date filters are
display-only filters on an existing run; changing them does not rebuild the central
database.

Back up PostgreSQL with `pg_dump`, test restores, rotate writer credentials, and remove
stale writer devices from the tailnet. Tailscale encrypts traffic between nodes; use
PostgreSQL TLS as an additional layer if your deployment policy requires it.

[grants]: https://tailscale.com/docs/reference/syntax/grants
[tags]: https://tailscale.com/kb/1068/acl-tags
[magicdns]: https://tailscale.com/docs/features/magicdns
