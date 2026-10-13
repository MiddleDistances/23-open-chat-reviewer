# Source adapters

Built-in adapters discover local Codex, Claude, Gemini, and Git records. They treat those
locations as read-only and return normalized values to the ingestion core.

## Built-in roots

| Provider | Suggested root | Typical evidence |
|---|---|---|
| Codex | `~/.codex` | session and history JSONL |
| Claude | `~/.claude` | project conversations and history JSONL |
| Gemini | `~/.gemini` | CLI conversation JSON documents |
| Git | `~/Projects` | commits and reflog evidence from discovered repositories |

The paths in this table are discovery suggestions/fallbacks. They are not part of the
adapter contract and must not be assumed to exist. Source roots are configured per
machine, and each provider may have multiple roots. A machine that has used more than
one login can, for example, configure both `/root/.codex` and
`/home/reviewer/.codex`. The same rule applies to Git roots when repositories live in
more than one top-level folder.

The Setup screen stores the machine-local choice in the Git-ignored
`.chatreview/source-roots.json`. The file contains paths only and is not a portable
machine identity or a database backup. A central web UI cannot edit the filesystem of a
different writer. Open Setup on that writer (or configure its environment before the
next sync); joining a Tailscale network never causes a network filesystem scan or a
remote source-folder discovery.

For environment-based configuration, use JSON arrays. JSON is intentional: it keeps
paths with spaces intact and makes multiple roots unambiguous.

```bash
export CHATREVIEW_CODEX_ROOTS='["/root/.codex","/home/reviewer/.codex"]'
export CHATREVIEW_CLAUDE_ROOTS='["/home/reviewer/.claude"]'
export CHATREVIEW_GEMINI_ROOTS='["/home/reviewer/.gemini"]'
export CHATREVIEW_GIT_ROOTS='["/home/reviewer/Projects","/home/reviewer/Archive Projects"]'
```

The singular `CHATREVIEW_CODEX_ROOT`, `CHATREVIEW_CLAUDE_ROOT`,
`CHATREVIEW_GEMINI_ROOT`, and `CHATREVIEW_GIT_ROOT` variables remain supported for
one-root legacy configurations. CLI root options may be repeated once per folder,
for example `--codex-root /root/.codex --codex-root /home/reviewer/.codex`; quote paths
with spaces. Removing a folder from the local configuration stops future discovery from
that folder, but does not delete records already archived from it.

File layouts are not public stability contracts. Each adapter carries a parser version;
when parsing changes, affected records can be deterministically reprojected from preserved
raw payloads.

## Adapter contract

A new adapter subclasses `ProviderAdapter` and implements:

- `name`: stable lowercase provider identity.
- `discover()`: return `SourceSpec` values for existing source files.
- `parse(data, source)`: map one object to a `ParsedRecord`.
- optionally `record_format()` and `parse_many()` for JSON documents containing several
  conversations.
- optionally `normalize_project()` for provider-specific workspace paths.

Parsing should retain messages, thinking, tool calls, tool results, error evidence, and
provider metadata without inventing outcomes. Use `add_fragment()` and
`extract_common_artifacts()` to share sanitization and artifact extraction.

Register the adapter in `_configured_adapters()` and the CLI adapter factory, add fixture
coverage for discovery and parsing, then document the new root variable. Do not let an
adapter write into the source directory or obtain database access.

## Git module

Git is enabled by default because commits and reflog events improve project timelines and
day tracking. It remains optional:

```bash
export CHATREVIEW_ENABLE_GIT=0
uv run open-chat-reviewer sync --no-git
```

The importer archives metadata and messages needed for evidence. It does not modify
repositories, check out branches, fetch remotes, or push changes.
