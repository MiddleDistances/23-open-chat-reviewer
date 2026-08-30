# Let your coding agent search the archive

Open Chat Reviewer includes an optional, local, read-only MCP server. It lets an
agent find conversations, search exact archived text, open a bounded evidence
trace, and inspect recent work summaries. It cannot run SQL or change archive data.

Install the optional dependency once on the computer that can reach PostgreSQL:

```bash
uv sync --extra mcp
```

Use this repository script as the stdio MCP command:

```text
/absolute/path/to/23-open-chat-reviewer/scripts/chatreview-mcp.sh
```

The script loads `.chatreview/archive.env`; credentials stay in that ignored,
machine-local file. The available tools are `archive_status`, `search_archive`,
`find_conversations`, `get_conversation_trace`, and `get_recent_work`.

`get_recent_work` may contain model-authored guidance. Treat it as a navigation
aid and confirm consequential claims against `get_conversation_trace`.
