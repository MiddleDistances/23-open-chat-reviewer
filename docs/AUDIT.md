# Open-source extraction audit

This repository was extracted from ChatReviewer as a focused, self-hostable chat-review
application.

## Retained

- PostgreSQL migrations, raw provenance, append-aware ingestion, canonical events.
- Codex, Claude, Gemini, and Git discovery/parsing.
- Sessions, traces, deterministic episodes, lexical search, optional semantic search.
- Labels, annotations, evidence exports, baseline reports.
- Evidence-bounded resume summaries with fingerprint reuse.
- Project/contributor registries, optional work categories, timesheets, and calendar UI.
- Worker orchestration, FastAPI, React UI, Compose database, and service templates.
- The original visual design specification in `design.md`.

## Removed

- R&D problem-family and relationship graph.
- Model-authored outcome judge and intervention registry.
- Episode pair laboratory, benchmark runner, and R&D proposal agent/MCP.
- Tax-specific classification language and private operational scripts.
- Hostnames, machine paths, storage layouts, credentials, and generated runtime archives.

## Boundary decisions

- Human labels and generic activity categories remain useful for chat review; they are not
  tax or legal classifications.
- Git/workload tracking remains enabled by default because it supports the same goal of
  understanding where time and attention went.
- Local Qwen is a documented recommendation, while the code depends only on a narrow
  provider protocol.
- The stable `chatreview` import and compatibility command remain to reduce extension
  breakage; the distribution and product are named `open-chat-reviewer`.

## Publication checklist

- Apache-2.0 license and community files included.
- `.chatreview/`, raw JSONL, databases, logs, and environment files ignored.
- CI covers Python lint/tests and the TypeScript test/build.
- Tests use synthetic paths, identities, and chat records.
- The public repository contains only the reviewed Git tree; runtime state remains local.

The maintainer should enable GitHub secret scanning and review Dependabot updates before
the first tagged release.
