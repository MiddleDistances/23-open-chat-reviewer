# Architecture

Open Chat Reviewer separates immutable source evidence from deterministic projections and
optional model-authored guidance.

```text
read-only source roots
  Codex | Claude | Gemini | Git
              |
              v
inventory -> raw records + hashes + byte locations (PostgreSQL authority)
              |
              v
canonical events -> sessions -> traces -> episodes
              |                     |
              |                     +-> optional summary provider -> resume cards
              +-> lexical search
              +-> optional semantic windows / pgvector
              +-> workload snapshots and calendar
              |
              v
FastAPI -> React UI / CLI / JSON and CSV exports
```

## Design rules

1. Source directories are read-only. Only PostgreSQL and `.chatreview/` are writable.
2. Raw payload bytes, hashes, source revision, byte offsets, and line numbers preserve the
   route back to evidence.
3. Derived rows can be rebuilt. Raw archive identity does not depend on a model.
4. Archive-derived facts and model-authored summaries remain separate and visibly typed.
5. A summary provider receives a bounded evidence prompt, never database or filesystem
   access. Its output must pass the strict `ResumeDraft` schema.
6. Unchanged evidence fingerprints reuse prior summaries.
7. Database advisory locks and filesystem locks prevent overlapping jobs.
8. Optional modules may be absent without making core archive health fail.

## Modules

### Ingestion core

`providers/` implements source adapters. `inventory.py` discovers sources, `ingest.py`
stores append-aware revisions and raw records, and `canonical.py` maps provider-specific
records into common events. A source adapter owns discovery and parsing, not database
policy.

### Review model

Sessions provide the conversation container. Traces reconnect messages, tool calls, and
tool results. Episodes deterministically group goal, attempt, and result evidence.
Annotations attach human labels and notes to stable session, event, window, or episode
keys.

### Search

Lexical search uses PostgreSQL full-text indexes and is always available. Semantic search
is an installable extra that writes versioned embedding runs. Hybrid search fuses the
candidate lists; semantic absence never changes raw or lexical results.

### Summaries

`summary_providers.py` defines the narrow provider protocol. `resume.py` prepares bounded
evidence packets, validates model JSON, records provenance and model identity, and reuses
unchanged results. Local Qwen is a recommendation, not an architectural dependency.

### Projects, Git, and workload

Git discovery contributes repository and commit evidence through the same raw archive.
Project aliases normalize machine-specific paths. Workload snapshots derive active
intervals from chat evidence, attribute them to contributors/projects, union overlap, and
split results using a configured IANA timezone. Activity categories are optional metadata.

### Runtime

The CLI and API are thin adapters over the same modules. `worker.py` sequences sync,
episode refresh, timesheet refresh, and optional summaries. PostgreSQL is the authority;
the web process is stateless apart from static UI assets.

## Extension seams

- Add a chat source by implementing the adapter contract in `providers/base.py` and
  registering it in the CLI provider factory.
- Add a model service by implementing `SummaryProvider` and exposing a zero-argument
  factory as `module:factory`.
- Add a derived view without mutating raw tables. Give it a corpus fingerprint,
  algorithm version, and rebuild path.
- Add a UI module through a distinct API boundary; do not make it a prerequisite for
  ingestion health.

The database decision is recorded in
[ADR 0001](adr/0001-postgresql-pgvector-archive.md).
