# Contributing

Thanks for improving Open Chat Reviewer. Bug reports, documentation fixes, setup
feedback, tests, and focused code changes are all welcome.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). By
submitting a contribution, you agree that it may be distributed under the project's
[Apache-2.0 license](LICENSE).

## Before you start

- Search the existing issues and pull requests before opening a duplicate.
- Open an issue before a large change, new provider, schema redesign, or public API
  change so scope and compatibility can be agreed first.
- Never post real chat content, credentials, database URLs, private paths, or unredacted
  logs. Use synthetic examples.
- Report vulnerabilities through [GitHub's private vulnerability reporting](https://github.com/MiddleDistances/23-open-chat-reviewer/security/advisories/new),
  not a public issue.

For a small, well-scoped fix, you can open a pull request directly.

## Development setup

```bash
git clone https://github.com/YOUR-USERNAME/23-open-chat-reviewer.git
cd 23-open-chat-reviewer
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

Run the checks for every area you change. The pull-request gate runs the Python suite on
Python 3.12 and 3.13 and runs the complete web lint, test, and build suite.

## Project invariants

Open Chat Reviewer handles private conversation archives. Contributions must preserve
these boundaries:

- Never add real chat records, database dumps, environment files, credentials, personal
  paths, or generated logs to fixtures.
- Treat configured Codex, Claude, Gemini, and Git directories as read-only inputs.
- Preserve raw payload identity and source provenance when changing parsers.
- Keep provider-specific parsing inside adapters.
- Add an ordered migration for schema changes; do not edit a migration already released.
- Keep model output out of canonical facts. Validate it at its module boundary.
- Give derived modules a deterministic rebuild or invalidation strategy.
- Update tests and the relevant document with behavior changes.

Read [the architecture guide](docs/ARCHITECTURE.md) before adding a source, model, or
derived module. Keep runtime secrets and machine-local state inside the Git-ignored
`.chatreview/` directory.

## Pull requests

1. Create a focused branch in your fork.
2. Add or update tests and documentation with the implementation.
3. Run the relevant local checks above.
4. Complete the pull-request template, including migration and privacy impact.
5. Respond to review comments with follow-up commits. Do not rewrite shared history after
   review has started unless a maintainer asks you to.

The `main` branch accepts changes through pull requests only. Required CI checks and
review conversations must be complete before merge. Maintainers may squash commits when
merging to keep the project history concise.

## Review standard

Maintainers evaluate whether a change is safe for private archives, compatible with the
documented architecture, tested in proportion to risk, migration-safe, understandable to
operators, and small enough to review reliably. A technically sound proposal may still
be declined when its ongoing maintenance cost or product scope is unclear.

See [GOVERNANCE.md](GOVERNANCE.md) for project roles and decision-making.
