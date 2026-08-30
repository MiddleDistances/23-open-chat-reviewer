# Open Chat Reviewer agent guide

PostgreSQL named by `CHATREVIEW_DATABASE_URL` is the runtime authority. `.chatreview/` is
Git-ignored machine-local state for secrets, locks, logs, reports, and exports.

- Treat Codex, Claude, Gemini, and Git roots as read-only inputs.
- Use `uv sync` and `uv run`; do not rely on system Python packages.
- Run `uv run open-chat-reviewer db doctor` before deployment and apply migrations
  deliberately with `uv run open-chat-reviewer db migrate`.
- Keep archive-derived facts separate from model-authored summaries.
- Never commit credentials, raw archives, SQLite/database files, generated logs, or real
  user paths.
- Preserve unrelated work in a dirty worktree.

Validate Python changes with `uv run ruff check src tests` and `uv run pytest -q`.
Validate UI changes with `bun run lint`, `bun run test`, and `bun run build` from `web/`.
See `docs/ARCHITECTURE.md` before adding a source, model, or derived module.
