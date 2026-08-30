# ADR 0001: PostgreSQL is the archive authority

Status: Accepted

## Decision

Use PostgreSQL as the sole authoritative store for raw source evidence, normalized
projections, review metadata, lexical indexes, optional vectors, and workload snapshots.
Use ordered SQL migrations and the pooled `chatreview.db` boundary. Do not maintain a
second SQLite dialect or a separate vector index as another authority.

## Context

Conversation archives are append-heavy, can be large, and need concurrent sync, review,
and search. The same raw evidence must support deterministic rebuilds and provenance-linked
exports without duplicating truth across local files.

## Consequences

- A PostgreSQL service is required even for a single-user installation.
- `pg_trgm` supports lexical retrieval and pgvector supports optional semantic indexes.
- Schema changes require explicit, ordered migrations and backup discipline.
- Optional semantic indexes are approximate projections and can always be rebuilt.
- Machine identity and source location remain metadata in the shared archive.
