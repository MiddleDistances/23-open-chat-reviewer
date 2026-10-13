## Outcome

<!-- What user-visible or operator-visible outcome does this change provide? -->

## Changes

<!-- Summarize the implementation. Link an issue with "Closes #123" when applicable. -->

## Validation

<!-- List the exact checks you ran and their results. -->

- [ ] Python checks: `uv run ruff check src tests` and `uv run pytest -q`
- [ ] Web checks, when relevant: `bun run lint`, `bun run test`, and `bun run build`
- [ ] Documentation updated when behavior or operator steps changed

## Safety and compatibility

- [ ] Fixtures, logs, and screenshots contain no private chats, credentials, database
      URLs, personal paths, or identifying data
- [ ] Source directories remain read-only
- [ ] Model-generated output remains separate from canonical archive facts
- [ ] Schema changes use a new ordered migration and include upgrade/recovery notes
- [ ] Breaking changes and deployment impact are described below

Migration, privacy, and compatibility notes:

<!-- Write "None" only after checking each category. -->
