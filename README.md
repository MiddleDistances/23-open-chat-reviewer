# Open Chat Reviewer

Open Chat Reviewer is a self-hosted archive and review workspace for local AI coding
conversations. It incrementally discovers Codex, Claude, and Gemini chat files, preserves
their raw provenance in PostgreSQL, reconstructs searchable conversations and work
episodes, and presents the result in a local web interface.

Git activity and overlap-aware workload calendars are included as an enabled-by-default
module. Evidence-bounded resume cards are optional and work with a local Qwen model,
the user's existing Codex/Claude/Gemini CLI login, hosted model gateways, Anthropic, or
a small custom provider plugin.

The recommended topology is one Tailscale-only central archive with small writer agents
on each computer. Every writer scans its local read-only chat directories into the same
PostgreSQL database, so the review and workload views span the user's actual machines
without copying raw archive files between them.

![Status: alpha](https://img.shields.io/badge/status-alpha-orange)
![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)

## What it includes

- Read-only discovery of Codex, Claude, Gemini, and Git source directories.
- Resumable, append-aware sync with raw payload hashes and exact source locations.
- PostgreSQL full-text search and optional pgvector semantic search.
- Deterministic goal/attempt/result episodes, session traces, annotations, and exports.
- Optional evidence-bounded summaries with fingerprint reuse for unchanged sessions.
- Setup-page summary controls that safely reuse supported coding-agent CLI subscriptions
  without copying their credentials into the application.
- Git-backed project history plus workload/timesheet calendars that avoid double-counting
  parallel chats for the same project.
- A FastAPI backend, responsive React UI, unattended worker, and Linux/macOS service
  templates.

The research graph, outcome-judging system, benchmark harness, and tax-specific reporting
from the original private application are intentionally not part of this repository.

## Quick start

Requirements: Python 3.12 or 3.13, [uv](https://docs.astral.sh/uv/), Docker with Compose,
[Tailscale](https://tailscale.com/download) for the recommended private multi-machine
setup, and optionally [Bun](https://bun.sh/) to build the UI.

```bash
git clone https://github.com/MiddleDistances/23-open-chat-reviewer.git
cd 23-open-chat-reviewer
scripts/bootstrap.sh
scripts/chatreview-sync.sh
scripts/chatreview-web.sh
```

When Tailscale is connected, open `http://<this-machine's-MagicDNS-name>:8765` from an
allowed tailnet device. Otherwise open <http://127.0.0.1:8765>. `bootstrap.sh` creates a private
`.chatreview/archive.env`, starts the bundled PostgreSQL/pgvector database, applies
migrations, and builds the UI when Bun is available. Its automatic network mode prefers
Tailscale and generates a random database password; set
`CHATREVIEW_INIT_NETWORK=loopback` to force a single-computer installation.

Review `.chatreview/archive.env` before the first sync. The generated defaults scan
`~/.codex`, `~/.claude`, `~/.gemini`, and `~/Projects` for Git repositories. Override
any root with the corresponding `CHATREVIEW_*_ROOT` variable. Source roots are inputs
only; Open Chat Reviewer writes to PostgreSQL and the Git-ignored `.chatreview/` runtime
directory.

For a first installation, read [Setup, scope, and storage](docs/SETUP_AND_STORAGE.md)
before syncing. It explains the central/writer choice, per-machine history scope,
reasoning retention/search/embedding controls, progress states, and exactly what Git
evidence is stored. A second computer does not see the first computer's local archive
until it is configured as a writer for the same central PostgreSQL database.

## Everyday commands

```bash
uv run open-chat-reviewer doctor
uv run open-chat-reviewer inventory
uv run open-chat-reviewer sync
uv run open-chat-reviewer refresh
uv run open-chat-reviewer status
uv run open-chat-reviewer search "database migration"
uv run open-chat-reviewer timesheets export --format csv
uv run open-chat-reviewer worker once
```

`chatreview` remains as a compatibility command. New documentation uses
`open-chat-reviewer`.

## Summarization providers

Summaries are off by default. The recommended privacy-first setup is a local Qwen
instruct model behind an OpenAI-compatible endpoint:

```bash
export CHATREVIEW_ENABLE_SUMMARIES=1
export CHATREVIEW_SUMMARY_PROVIDER=openai-compatible
export CHATREVIEW_SUMMARY_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
export CHATREVIEW_SUMMARY_BASE_URL=http://127.0.0.1:8000/v1
uv run open-chat-reviewer resume refresh
```

The same adapter supports model services that expose compatible Chat Completions APIs,
including Alibaba Model Studio, Hugging Face Inference Providers, OpenRouter, and OpenAI.
Anthropic has a native adapter. A `module:factory` plugin seam supports any other provider
without changing the archive core. Keep API keys only in `.chatreview/archive.env`; the
CLI does not accept keys as command-line arguments.

See [Model providers](docs/MODEL_PROVIDERS.md) for configuration and the provider
contract.

## Workload and day tracking

The workload module combines chat sessions with optional Git evidence. It builds
immutable snapshots, splits intervals at midnight in the configured IANA timezone, and
unions overlapping intervals for the same contributor/project before reporting totals.
It is a record-organizing aid, not payroll or billing authority.

Disable Git discovery with `CHATREVIEW_ENABLE_GIT=0` or `--no-git`. Configure local day
boundaries with `CHATREVIEW_TIMEZONE`, for example `Australia/Perth`.

## Architecture and operations

- [Architecture](docs/ARCHITECTURE.md)
- [Setup, scope, and storage](docs/SETUP_AND_STORAGE.md)
- [Source adapters](docs/SOURCE_ADAPTERS.md)
- [Sync and worker operations](docs/SYNC_OPERATIONS.md)
- [Tailscale central archive and remote writers](docs/TAILSCALE_MULTI_MACHINE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Audit and extraction boundary](docs/AUDIT.md)
- [Visual design language](design.md)

## Development

```bash
uv sync
uv run ruff check src tests
uv run pytest -q
cd web && bun install --frozen-lockfile && bun run test && bun run build
```

Database tests use `CHATREVIEW_TEST_DATABASE_URL`; by default they expect PostgreSQL on
port `6543`. See [CONTRIBUTING.md](CONTRIBUTING.md) for a complete setup.

## Privacy and security

Raw chat archives often contain source code, paths, prompts, and credentials. Automatic
bootstrap binds to an active Tailscale interface when available and otherwise falls back
to loopback. The web app has no built-in multi-user authentication. Do not expose it to
the public internet; restrict both the UI and PostgreSQL ports with tailnet grants and read
[SECURITY.md](SECURITY.md) before deployment.

## License

Apache License 2.0. See [LICENSE](LICENSE).
