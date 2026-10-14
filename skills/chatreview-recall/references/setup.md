# Setup and diagnosis

Guidance checked 2026-10-14 against the public repository's compact recall
contract and official [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp)
and [skill customization documentation](https://learn.chatgpt.com/docs/customization/overview).

The public ChatReviewer implementation exposes seven tools through stdio:
`archive_status`, `search_archive`, `find_conversations`,
`get_conversation_trace`, `get_recent_work`, `find_prior_work`, `read_prior_work`.
It does not mount an HTTP MCP endpoint. Old private deployments may differ;
inspect the actual launcher and checkout rather than inferring their transport.

First check the tools exposed to the current session. If compact tools are
present, try a small search and read a returned anchor. Do not replace a working
MCP connection with direct database queries because another environment lacks
the optional dependency.

For a broken connection, inspect `codex mcp list` and only the relevant server
configuration, without printing credentials. User configuration defaults to
`~/.codex/config.toml`; a trusted project's `.codex/config.toml` can also apply.
Inspect `command` versus `url`, `enabled`, `enabled_tools`, `disabled_tools`,
the environment file and whether that launcher exists on the executing host.
Tool deny lists apply after allow lists. Restart/reconnect the affected client
after changes, then verify its actual tool catalog.

A public-server registration uses this shape, with absolute host-local paths:

```toml
[mcp_servers.chatreview-recall]
command = "/absolute/deployed-repo/scripts/chatreview-mcp.sh"
enabled = true

[mcp_servers.chatreview-recall.env]
CHATREVIEW_ENV_FILE = "/absolute/machine-local/archive.env"
```

The central installation selects its existing `live.env`; collectors retain
their own archive configuration and GPUBox retains its semantic-worker
environment. The name alone does not prove which database it reaches. Preserve
credentials, machine identity, source roots and database-role boundaries.

Diagnose missing MCP support in the launcher's own `.venv`, not system Python
or an unrelated checkout. From the selected repository use `uv sync --frozen
--extra mcp` for a recall-only environment. For a service environment already
using semantic dependencies, preserve its extras with `uv sync --frozen
--all-extras`. Install only as authorized; skill guidance alone does not grant
permission to mutate another service. No database migration is needed for recall.

For current Codex clients, user skills live in `~/.agents/skills`; repository
skills live in `.agents/skills`. This project's installer also updates
`~/.codex/skills` for clients using that compatibility location, preventing an
older same-named copy from lingering. A local skill archive does not install
an MCP server or make localhost paths available to a cloud client.

After an authorized update, verify the seven-tool catalog, a successful
`find_prior_work` call, and `read_prior_work` using that response's target.
Successful tool discovery alone does not prove database reads work. Report the
host, launcher and actual error if a call fails. Do not broaden database grants
or switch to owner credentials just to make a diagnostic succeed.
