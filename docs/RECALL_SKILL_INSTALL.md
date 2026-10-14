# Install updated recall guidance

Guidance version: 2026-10-14. This package updates skill files only. It contains
no credentials, archives or database files and does not change background jobs,
MCP registration or database grants.

Give the downloaded bundle and these instructions to the local agent:

> Install the bundled chatreview-recall skill with backups. Preserve my existing
> credentials, machine identity, source roots and background services. Check the
> actual user and trusted-project MCP registrations. For the public server use
> stdio, not the old web `/mcp` URL. Verify the current client's tool discovery
> and real compact search/read calls; report anything still blocked. Update only
> stale recall guidance in an existing data-source skill, preserving other routes.

From the extracted bundle or repository, use a Python 3.12+ environment:

```bash
# In the existing repository, use its uv environment:
uv run --no-sync python scripts/install-recall-skill.py
# For the standalone extracted bundle, an existing Python 3.12+ also works:
python3 scripts/install-recall-skill.py
```

The installer backs up existing copies and installs the complete skill into
`~/.agents/skills/chatreview-recall` and `~/.codex/skills/chatreview-recall`, checking
file hashes. It prints the backup path and receipt. `--home` supports an isolated
installation test. MCP configuration is untouched.

If recall is already exposed, use it before trying to fix another environment.
If registration is stale, inspect `codex mcp list`, relevant configuration and the
selected launcher's `.venv`. Back up configuration before replacing only the
`chatreview-recall` registration. Use the existing host-local environment file;
never fetch someone else's credentials. An example for an installed public repo:

```bash
# Replace both values with existing absolute paths on THIS machine.
CHATREVIEW_REPO=/absolute/deployed-repo
CHATREVIEW_LOCAL_ENV=/absolute/existing-machine-local.env
# Preserve semantic extras if this environment also runs semantic services.
uv sync --project "$CHATREVIEW_REPO" --frozen --extra mcp
codex mcp add chatreview-recall \
  --env "CHATREVIEW_ENV_FILE=$CHATREVIEW_LOCAL_ENV" \
  -- "$CHATREVIEW_REPO/scripts/chatreview-mcp.sh"
```

If the CLI refuses to replace an existing entry, back it up and remove only that
named entry before adding the corrected one. Check trusted-project overrides and
tool filters too. No database migration or new HTTP endpoint is required.

Restart/reconnect the affected MCP server or client and confirm the refreshed
skill is available. Verify seven tools, call `find_prior_work` with a distinctive
query and limit 1, then pass a returned anchor's `read_target` arguments to
`read_prior_work`, omitting `tool`. Keep numeric IDs and the unit key. A successful
installation alone does not establish successful archive reads.

Current official sources, checked 2026-10-14:
- [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp)
- [Codex skill locations and customization](https://learn.chatgpt.com/docs/customization/overview)

Project contract: [compact recall](COMPACT_RECALL.md). The standalone bundle
includes the skill's setup reference with the relevant contract and source links.
