# Contributing

Thanks for improving Open Chat Reviewer. Please keep changes evidence-preserving,
provider-neutral, and safe for private chat archives.

## Development setup

```bash
uv sync
docker compose up -d db
```

The regular app database uses port `54329`. Tests default to port `6543`, so either run a
second disposable PostgreSQL/pgvector instance there or set
`CHATREVIEW_TEST_DATABASE_URL` to a test database. Tests create and remove isolated
schemas.

```bash
uv run ruff check src tests
uv run pytest -q
cd web
bun install --frozen-lockfile
bun run lint
bun run test
bun run build
```

## Change guidelines

- Never add real chat records, database dumps, environment files, credentials, personal
  paths, or generated logs to fixtures.
- Preserve raw payload identity and source provenance when changing parsers.
- Keep provider-specific parsing inside adapters.
- Add an ordered migration for schema changes; do not edit a migration already released.
- Keep model output out of canonical facts. Validate it at its module boundary.
- Give derived modules a deterministic rebuild or invalidation strategy.
- Update tests and the relevant document with behavior changes.

Open a focused pull request describing the user-facing outcome, migration impact, privacy
impact, and validation performed.
