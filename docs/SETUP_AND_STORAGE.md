# Setup, scope, and storage

This page explains the setup choices that matter before the first large sync. The
database is the archive authority; the source folders on each computer remain
read-only inputs. Use this page alongside [Sync and worker operations](SYNC_OPERATIONS.md)
and [Tailscale central archive and remote writers](TAILSCALE_MULTI_MACHINE.md).

## Choose a summary agent

The Setup & storage screen contains a machine-local **Focus summaries** control. It can
use a configured local Qwen endpoint or a detected Codex, Claude, or Gemini CLI. CLI
choices reuse the login already active for the operating-system user running the web
service; the GUI does not ask for or display a token. Select a bounded history window
and choose **Save and run summaries**. Progress is recorded in the ignored
`.chatreview/summary-run.json` file.

Only fixed adapters are available. A free-form command field is deliberately excluded
because the setup page may be reachable from another tailnet machine and arbitrary CLI
arguments would be equivalent to remote command execution. For unattended refreshes,
enable `CHATREVIEW_ENABLE_SUMMARIES=1`; the worker honors the saved GUI selection.

## Choose the topology

There are two supported roles:

| Role | Runs on | Writes | Does not run |
|---|---|---|---|
| Central | One trusted archive computer | PostgreSQL, web UI, worker, and derived projections | — |
| Writer | Each other source computer | Its local source observations and canonical rows in the central PostgreSQL database | Migrations, the central worker, or a second web archive |

The archive is not automatically present on every computer. A new computer must be
installed as a writer and pointed at the central database. It contributes only the
chat and Git roots configured on that computer. Its machine ID is stored with every
source so identical paths on two computers do not collapse into one source.

The Setup page does not perform a LAN or Tailscale scan. Choose **Add another machine**,
follow the writer guide on that computer, run its first sync, then choose **Check shared
archive**. The machine is discovered from its PostgreSQL registration. Setup-button
behavior and feedback identifiers are documented in [UI action and feedback rules](UI_ACTIONS.md).

For a single-computer archive, use the central role with a loopback bind. For multiple
computers, put PostgreSQL, the web process, and the derived worker on the central node
and connect writer nodes over a private Tailscale network. The web process has no
built-in user authentication; network access is part of the security boundary.

## First-run checklist

On the central computer:

```bash
scripts/bootstrap.sh
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer db migrate
```

Review the generated `.chatreview/archive.env` before syncing. It is local, ignored,
and mode `0600`; do not paste its database URL into chat, a ticket, or source control.
Run an inventory first when the source corpus is large:

```bash
uv run open-chat-reviewer inventory --no-git
```

Enable Git only after confirming the project root. Git discovery is metadata-only (see
below), but it can add many repositories to the first scan.

On each additional computer:

1. Clone the same release of this repository and run `uv sync`.
2. Obtain a dedicated writer environment from the central operator.
3. Set that computer's Codex, Claude, Gemini, and optional Git roots.
4. Keep the generated machine ID stable for the life of that writer.
5. Run `db doctor`, `inventory`, and then the resumable sync wrapper.

The normal writer command is:

```bash
scripts/chatreview-sync.sh
```

Do not copy a writer's `.chatreview` directory or machine ID to another computer. Do
not run migrations, the web server, or the central worker from a writer. The complete
credential and Tailscale procedure is in the multi-machine guide.

## Scope choices

The setup screen should make two scopes explicit because they have different cost and
correctness implications:

### Archive scope

This controls what a writer reads from its local sources. Choose providers, source
roots, and an optional earliest date before the first import. The default is the full
available local history. A date-limited import is a deliberate retention choice: files
outside the selected range are not needed for that initial archive, and changing the
range later requires a new sync with the broader scope. The source files are never
edited or deleted by the importer.

The archive scope is per writer. A central computer may contain old history from one
machine and only recent history from another. The UI should show the effective earliest
and latest timestamps per machine/provider rather than implying that the whole database
has one universal start date.

### Semantic scope

Semantic windows and embeddings are a rebuildable projection of the canonical archive.
Their setup controls should include:

- providers and projects;
- semantic date-from and date-to;
- included event kinds;
- whether readable reasoning text is searchable;
- whether readable reasoning text is embedded;
- whether tool/context/compaction material is embedded;
- model, dimensions, window size, and overlap.

The semantic date scope is independent of archive retention. It changes the next
semantic build, not the raw archive. The map's date filter is a view-time filter over
an existing run; it should not silently rebuild embeddings. A map hover displays a
short preview of the actual text sent to the embedding model (the semantic window),
with project/provider/date metadata. It must not use a repeated session heading as the
dot's identity.

## Reasoning and privacy controls

Reasoning has several representations and they must not be conflated:

| Representation | Purpose | Default policy |
|---|---|---|
| Provider-native or encrypted trace in the raw payload | Exact provenance and future parser recovery | Preserve only when the operator accepts the extra storage and sensitivity |
| Readable normalized reasoning text | Exact lexical review and evidence display | Searchable only when explicitly enabled |
| Readable reasoning text in semantic windows | Similarity and map projection | Embed only when explicitly enabled |
| Model-authored summary/resume card | Guidance, not source evidence | Off unless a provider is configured |

The preservation choice is separate from search and embedding choices. Excluding
reasoning from semantic projection must not be described as deleting the source
record. Conversely, preserving an encrypted raw field does not mean that its opaque
bytes are useful search text. A setup preview should report counts and estimated bytes
for each category before a build starts, and the status view should retain the policy
used for each derived run.

Raw evidence and canonical text are governed by the archive's provenance contract;
semantic windows, embeddings, clusters, and summaries can be deleted and rebuilt from
the retained evidence. If raw encrypted reasoning was not retained, a later rebuild
cannot recreate it from the source archive. Treat that as a one-way retention decision
and record it in the local setup report.

## What is stored

The PostgreSQL archive contains the following layers:

1. **Source registry and provenance.** Machine identity, provider, source path,
   source kind, revision/fingerprint, byte or line location, and parser metadata.
2. **Raw records and payloads.** Hash-addressed provider records retained for exact
   provenance and append-aware reprocessing, subject to the selected raw retention
   policy. These can contain prompts, responses, tool calls, paths, and provider
   metadata from the configured source roots.
3. **Canonical archive.** Sessions, events, text units, artifact references, and
   normalized fields used for exact search and deterministic episode/timeline logic.
4. **Rebuildable projections.** Episodes, workload snapshots, semantic windows,
   embeddings, clusters, annotations, and optional resume cards. A model-authored
   card is labeled as guidance and is never promoted to canonical evidence.
5. **Git evidence.** Repository identity, normalized remote/project, branch/ref or
   reflog context, commit IDs and parent IDs, author/timestamps, commit messages,
   changed file names/status, and source locations. Open Chat Reviewer does **not** copy
   Git blobs, patches, full file contents, or the whole repository history into the
   database.

It does not recursively archive arbitrary files from a checkout, the operating system,
or Git object storage. It discovers only the configured provider roots and Git
repositories. The source folders are inputs; PostgreSQL and the ignored `.chatreview/`
directory are the writable destinations. `.chatreview/` contains configuration,
secrets, locks, logs, reports, and exports, not a second authoritative database.

## Why a build can be large

Storage is usually dominated by deduplicated normalized content and its PostgreSQL
indexes, followed by raw provider payloads and derived text. A semantic build adds
windows, embeddings, and clustering indexes; it does not copy Git files. Exact raw
reasoning can be large even when its readable summary is small, so the setup preview
should show both logical bytes and the resulting database estimate.

For a very large first import, use the deliberate index-suspension and rebuild commands
documented in [Sync and worker operations](SYNC_OPERATIONS.md). They are maintenance
operations, not data deletion. Monitor PostgreSQL disk headroom and keep a tested backup
before material schema or retention changes.

## Progress and recovery

Sync is append-aware and resumable. A stopped process does not require starting the
corpus from zero; completed source revisions and offsets are reused. The setup/status
view should expose:

- current machine and role;
- discovered files and bytes by provider;
- processed, skipped, failed, and remaining source counts;
- canonical events/text units and raw payload bytes written;
- semantic windows completed and embedding/model status;
- last successful sync, refresh, and semantic run timestamps;
- the next safe action or blocking error.

The CLI equivalents are:

```bash
uv run open-chat-reviewer status
uv run open-chat-reviewer db doctor
uv run open-chat-reviewer inventory --no-git
```

After a non-empty sync, refresh deterministic projections intentionally. Build semantic
indexes separately because model downloads and GPU use can be substantial:

```bash
uv run open-chat-reviewer refresh
uv run open-chat-reviewer semantic refresh --no-reasoning \
  --date-from 2026-01-01 --date-to 2026-08-30
```

For a new archive that must omit opaque encrypted reasoning before PostgreSQL
persistence, set `CHATREVIEW_RAW_REASONING_RETENTION=redact` in the machine-local,
Git-ignored `.chatreview/archive.env` before its first sync. The default is `preserve`.
Redaction keeps a marker, the original byte count, and a SHA-256 digest, but it is a
one-way loss of those provider bytes from the database. Changing this setting later
creates new source revisions; it does not shrink already retained payloads.

Inspect `.chatreview/logs/` and the status output before retrying a failed run. Never
repair an ingestion problem by editing or deleting source chat files.
