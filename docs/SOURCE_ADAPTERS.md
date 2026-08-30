# Source adapters

Built-in adapters discover local Codex, Claude, Gemini, and Git records. They treat those
locations as read-only and return normalized values to the ingestion core.

## Built-in roots

| Provider | Default root | Typical evidence |
|---|---|---|
| Codex | `~/.codex` | session and history JSONL |
| Claude | `~/.claude` | project conversations and history JSONL |
| Gemini | `~/.gemini` | CLI conversation JSON documents |
| Git | `~/Projects` | commits and reflog evidence from discovered repositories |

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
