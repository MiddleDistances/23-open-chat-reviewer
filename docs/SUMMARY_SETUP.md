# Summary setup

Open Chat Reviewer can make resume cards from a local model, an existing coding-agent
login, or an OpenAI-compatible service. The archive, exact search, workload calendar,
and semantic map do not require summaries. A summary provider is an optional reader of
the archive, not part of the database or ingestion path.

This guide is written so that a beginner can follow it themselves or hand it to their
coding agent. The agent may inspect the machine, configure an already-running service,
and run bounded checks. It must ask before installing GPU drivers, downloading a large
model, changing firewall/Tailscale policy, or changing database credentials.

## The one decision that matters

The summary provider must be reachable **from the computer running the Open Chat
Reviewer web process and worker**. It does not matter where the source writers are. A
GPU on a laptop is useful only to a ChatReviewer process on that laptop; a GPU on a
separate computer needs a private URL or a tunnel to the central ChatReviewer machine.

| Choose this | Best for | What ChatReviewer needs |
| --- | --- | --- |
| Existing coding-agent login | Most users who already use Codex, Claude, or Gemini | A signed-in local CLI; no model URL or API key |
| GPU on this computer | A private, self-hosted model with one machine | An OpenAI-compatible server on `127.0.0.1` |
| GPU on another computer | A central archive with a stronger GPU elsewhere | A Tailscale-only URL or an SSH tunnel visible from the central machine |
| Hosted API | Users who do not want to operate a model server | An HTTPS base URL, model name, and API key |

The connection shape is always:

```text
Open Chat Reviewer web/worker  ── OpenAI-compatible HTTP ──>  model server  ──>  GPU
        (central archive machine)                              (local or remote)
```

The model server owns model files, CUDA/ROCm drivers, batching, and GPU selection.
ChatReviewer sends one bounded evidence packet and expects a schema-valid JSON resume
card. ChatReviewer does not install drivers, discover arbitrary model servers, copy CLI
tokens, or manage the model process.

## Let your AI agent set it up

The Setup page now builds this prompt for you: choose one of the four provider cards,
then press **Copy agent handoff**. If you are working from the README, copy the generic
version below into the coding agent on the machine where the Open Chat Reviewer web
process runs.

```text
Configure Open Chat Reviewer summaries for the current installation.

Safety and scope:
- Work only on the Open Chat Reviewer installation and its ignored .chatreview state.
- Never print, commit, or paste database URLs, API keys, CLI tokens, or raw chat text.
- Treat Codex, Claude, Gemini, and Git directories as read-only.
- Do not change PostgreSQL credentials, migrations, source archives, or firewall rules.
- Do not install GPU drivers, download a large model, or change Tailscale ACL/grants
  without showing me the exact action and asking for confirmation first.
- Prefer an existing working endpoint or signed-in CLI over installing another provider.

Inspect first:
1. Find the repository root and read AGENTS.md.
2. Find the effective ChatReviewer environment file, `CHATREVIEW_DATA_DIR`, and the
   web/worker service units. Pass that exact data directory to every summary command.
3. Check whether a configured OpenAI-compatible endpoint responds to GET <base>/models.
4. Check whether Ollama, vLLM, llama-server, or another compatible server is already
   running locally. Check for an NVIDIA/AMD GPU only as a read-only observation.
5. Check whether the required Codex, Claude, or Gemini CLI is installed and already
   authenticated. Never read its token files.
6. If the model is on another computer, check for an existing Tailscale connection or
   SSH access. Test from the central ChatReviewer machine, not only from this shell.

Choose the least invasive working route:
- signed-in CLI: use codex-cli, claude-cli, or gemini-cli;
- local GPU: use the already-running localhost OpenAI-compatible server;
- remote GPU: prefer a private Tailscale URL or an SSH tunnel;
- hosted service: use the user-provided HTTPS endpoint and key.

Use the repository's fixed summary commands; do not rewrite archive.env by hand:
- signed-in CLI: `uv run open-chat-reviewer summary use codex-cli --data-dir <effective-data-dir>` (or claude-cli/gemini-cli)
- endpoint: `uv run open-chat-reviewer summary probe --base-url <url> --model <id> --data-dir <effective-data-dir>`
- save endpoint: `uv run open-chat-reviewer summary configure --base-url <url> --model <id> --disable-thinking --data-dir <effective-data-dir>`
- select endpoint: `uv run open-chat-reviewer summary use qwen --data-dir <effective-data-dir>`

The commands write only credential-free settings to the mode-0600, Git-ignored
.chatreview/summary-provider.json. If an API key is required, use the existing
CHATREVIEW_SUMMARY_API_KEY environment variable; never pass it as a command argument.

For an OpenAI-compatible provider:
1. Verify <base-url>/models and use the exact returned model id.
2. Run a small completion or the smallest available provider health check.
3. Save through `summary configure`, then select it through `summary use qwen`.
4. Verify the Setup status reports the selected provider as Ready.
5. Source the effective environment file without printing it, then run one bounded test:
   `uv run open-chat-reviewer resume refresh --days 7 --limit 1 --per-project-limit 1 --data-dir <effective-data-dir>`.

Report only the provider kind, endpoint host/port without credentials, model id,
service readiness, and generated/reused/failed counts. If anything is ambiguous or a
high-impact action is needed, stop and ask instead of guessing.
```

The agent should finish with a test result, not just a changed environment file. A
successful `/models` request proves that the route is reachable; the bounded resume
refresh proves that the selected model can return the structured output ChatReviewer
needs.

## Option 1: use an existing CLI login

This is the smallest setup for people who already pay for or use a coding agent. The
CLI remains the owner of its login and subscription. ChatReviewer invokes a fixed,
non-interactive adapter and passes a bounded evidence packet on standard input; it does
not read or copy the CLI's credential files.

Sign in using the CLI's own documented flow, then choose the matching provider:

| CLI | Provider value | Login documentation |
| --- | --- | --- |
| Codex | `codex-cli` | [Codex authentication](https://developers.openai.com/codex/auth/) |
| Claude Code | `claude-cli` | [Claude Code setup](https://docs.anthropic.com/en/docs/claude-code/overview) |
| Gemini CLI | `gemini-cli` | [Gemini CLI repository](https://github.com/google-gemini/gemini-cli) |

Select the signed-in CLI with one local command:

```bash
uv run open-chat-reviewer summary use codex-cli
```

Use `claude-cli` or `gemini-cli` instead when that is the login you want. The CLI
supplies its normal account default; ChatReviewer neither reads nor copies its login.
Run a bounded check:

```bash
uv run open-chat-reviewer resume refresh --days 7 --limit 1 --per-project-limit 1
```

The browser setup control can select the same fixed provider identifiers. If the card
says that the CLI is not ready, authenticate with the CLI on the same operating-system
user that runs the ChatReviewer service; signing in as a different user does not make
that login available to the service.

## Option 2: GPU on the same computer

Run a model server on the central ChatReviewer machine and keep it on loopback. The
server may use CUDA, ROCm, Apple hardware acceleration, or CPU fallback; ChatReviewer
does not need to know which one.

### Ollama: simplest local route

Install Ollama using its [official installation instructions](https://ollama.com/download),
then use the Ollama documentation for the model you choose. Pulling a model is a large
download and may use substantial disk space, so an agent must show the model name and
size and ask before doing it.

After the server is running, verify the OpenAI-compatible endpoint. Ollama's default
OpenAI-compatible base URL is `http://127.0.0.1:11434/v1`:

```bash
curl -fsS http://127.0.0.1:11434/v1/models
```

Use the exact model id returned by that request:

```bash
uv run open-chat-reviewer summary configure \
  --base-url http://127.0.0.1:11434/v1 \
  --model the-model-id-from-v1-models \
  --disable-thinking
uv run open-chat-reviewer summary use qwen
```

See Ollama's [OpenAI compatibility documentation](https://docs.ollama.com/api/openai-compatibility)
for the supported route and request shape.

### llama.cpp: GGUF and advanced local deployments

Use a CUDA/ROCm-capable build as described by the
[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
The server should stay on loopback and expose an OpenAI-compatible port. A typical
already-installed server looks like this:

```bash
llama-server \
  -m /path/to/model.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --alias local-summary-model
```

Then configure:

```bash
uv run open-chat-reviewer summary configure \
  --base-url http://127.0.0.1:8080/v1 \
  --model local-summary-model \
  --disable-thinking
uv run open-chat-reviewer summary use qwen
```

`--alias` is important: it gives the server a stable API model id even when the local
filename changes. Do not copy this example until the model format, accelerator build,
and memory requirements have been checked.

### vLLM: NVIDIA/performance route

Use the [vLLM quickstart](https://docs.vllm.ai/en/latest/getting_started/quickstart/)
for installation and model-specific flags. Keep the listener on `127.0.0.1` when
ChatReviewer and vLLM share a computer. The resulting configuration has the same shape:

```bash
uv run open-chat-reviewer summary configure \
  --base-url http://127.0.0.1:8000/v1 \
  --model the-model-id-returned-by-v1-models \
  --disable-thinking
uv run open-chat-reviewer summary use qwen
```

The exact model, quantization, tensor-parallel settings, and GPU memory limits are
deployment-specific. An agent may inspect them and suggest a command, but should ask
before pulling a model or changing a running service.

## Option 3: GPU on another computer

Run the complete model server on the GPU computer. ChatReviewer should call that model
server over a private path. It is simpler and safer than trying to distribute one model
between two machines.

Do not use the llama.cpp RPC backend as a beginner remote-GPU setup. The upstream
documentation describes that facility as experimental and warns that it is not suitable
for an open network. A normal HTTP model server behind Tailscale or an SSH tunnel keeps
the boundary clear: the GPU machine owns inference and the central machine is just a
client.

### Recommended: Tailscale Serve

On the GPU machine:

1. Install Tailscale and sign in to the same tailnet as the central archive.
2. Run the model server on `127.0.0.1:8000` (or its chosen local port).
3. Verify it locally with `curl http://127.0.0.1:8000/v1/models`.
4. Use [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) to expose
   that localhost service only inside the tailnet. Review the command for the installed
   Tailscale version before running it.
5. From the central machine, test the generated MagicDNS URL, for example:

   ```bash
   curl -fsS https://gpu-machine.example-tailnet.ts.net/v1/models
   ```

Save that HTTPS URL on the central archive machine:

```bash
uv run open-chat-reviewer summary configure \
  --base-url https://gpu-machine.example-tailnet.ts.net/v1 \
  --model the-model-id-from-v1-models \
  --disable-thinking
uv run open-chat-reviewer summary use qwen
```

Use a Tailscale grant that permits only the central archive machine to reach the model
port. Tailscale grants are deny-by-default and can restrict access by source, device,
and port; see the [grants documentation](https://tailscale.com/docs/features/access-control/grants).
If the model server supports an API key, use one as a second boundary and store it only
in `.chatreview/archive.env` with mode `0600`.

### Fallback: SSH tunnel

Keep the model server bound to localhost on the GPU computer, then create the tunnel on
the central ChatReviewer computer:

```bash
ssh -N -T \
  -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18000:127.0.0.1:8000 \
  user@gpu-machine
```

The central ChatReviewer configuration uses the local end of the tunnel:

```bash
uv run open-chat-reviewer summary configure \
  --base-url http://127.0.0.1:18000/v1 \
  --model the-model-id-from-v1-models \
  --disable-thinking
uv run open-chat-reviewer summary use qwen
```

Test from the central machine while the tunnel is running:

```bash
curl -fsS http://127.0.0.1:18000/v1/models
```

For unattended summaries, run the tunnel under a user service or another supervised
mechanism with a restricted SSH key. Do not put a password in a script. The
[OpenSSH manual](https://man.openbsd.org/ssh) documents local port forwarding and the
options used above.

### Advanced: direct Tailscale address

A model server may listen on the GPU computer's Tailscale address instead of using Serve
or SSH, but this requires a firewall, an access policy, and model-server authentication.
Use this only when the operator understands those controls. Never expose an unauthenticated
model server on `0.0.0.0` or a public router.

## Put the settings in the right place

The summary settings belong to the **central ChatReviewer process**, not to every writer
computer. The model may run on another machine, but the saved URL must be reachable
from the central machine.

`summary configure` atomically writes the non-secret endpoint, model id, and thinking
preference to:

```text
<repository>/.chatreview/summary-provider.json
```

The file is owner-only (`0600`) and is loaded dynamically by the GUI, CLI, and worker.
It contains no API key or database URL. Use the command instead of editing this JSON.
The selected `qwen` or CLI adapter is stored separately in
`.chatreview/summary-agent.json`. An existing `summary-provider.json` takes precedence
over compatibility environment values for OpenAI-compatible runs.

Keep secrets in the ignored environment file:

```text
<repository>/.chatreview/archive.env
```

The file should be readable only by its owner:

```bash
chmod 600 .chatreview/archive.env
```

Do not put an API key in the URL, shell history, a screenshot, a Git commit, or the
AI-agent handoff report. `CHATREVIEW_SUMMARY_HEADERS_JSON` can add provider-specific
headers, but treat it as secret configuration when it contains credentials.

Only environment changes, such as adding an API key, require a service restart. For the
bundled Linux user services:

```bash
systemctl --user restart open-chat-reviewer-web.service
systemctl --user restart open-chat-reviewer-worker.service
```

If a service is not installed, restart the process started by
`scripts/chatreview-web.sh` or `scripts/chatreview-worker.sh` instead. An environment
file change does not alter an already-running process.

Browser endpoint probe/save actions are local-only by default. When Setup is opened
from another machine over Tailscale, copy the generated agent handoff and run it on the
central ChatReviewer machine. An operator may explicitly allow private remote actions
with `CHATREVIEW_ALLOW_REMOTE_SUMMARY_SETUP=1`, but should do so only when the web UI is
protected by a narrow Tailscale policy.

## Verify in three small steps

### 1. Verify the model route

Use the built-in probe, which validates the URL, blocks redirects, bounds the response,
and checks the selected model id:

```bash
uv run open-chat-reviewer summary probe
```

For a keyed service, load the ignored environment without printing the key, then run
the same probe:

```bash
source .chatreview/archive.env
uv run open-chat-reviewer summary probe
```

The response must contain the exact saved model identifier. A successful network
connection with the wrong model id is still a failed setup.

### 2. Verify ChatReviewer sees the provider

Run the smallest real summary batch:

```bash
uv run open-chat-reviewer resume refresh \
  --days 7 \
  --limit 1 \
  --per-project-limit 1
```

The command should finish with generated, reused, and failed counts. It is intentionally
bounded so the first test does not spend hours or send the whole archive to a provider.
Increase `--days` and `--limit` only after checking the result.

### 3. Verify the GUI and worker

Reload Setup → Focus summaries. The selected provider should say **Ready**. For
unattended work, confirm the worker service has the same environment file and then check:

```bash
uv run open-chat-reviewer status
journalctl --user -u open-chat-reviewer-worker.service --since '15 minutes ago'
```

The provider status and logs may report the endpoint host, model, or error category; they
must not report credentials or raw evidence packets.

## Troubleshooting

| Symptom | Likely cause | Next check |
| --- | --- | --- |
| Local Qwen says “Configure” | No endpoint/model has been saved yet | Click the Qwen card to open the guided setup, or run `summary configure` and `summary use qwen` on the central machine |
| `/v1/models` refuses the connection | Model server or SSH tunnel is stopped, or the port is wrong | Run the request from the central machine; check the model server/tunnel process |
| `/v1/models` returns 401/403 | API key or Tailscale policy is missing | Test the key privately and review the narrow Tailscale grant |
| Model not found | Display name differs from API model id | Use the exact `id` returned by `/v1/models` |
| Route works but JSON summary fails | Thinking output, unsupported structured output, or too little output budget | Try an instruct model; set `CHATREVIEW_SUMMARY_DISABLE_THINKING=1`; inspect the provider error without exposing evidence |
| Works in a terminal but not in the GUI | The GUI service runs as another user or reads another env file | Check the service `ExecStart`/`CHATREVIEW_ENV_FILE` and restart that service |
| Works on the GPU computer but not centrally | The URL is local to the wrong computer | Test the same URL from the central ChatReviewer machine; use Tailscale Serve or an SSH tunnel |
| The first run is unexpectedly expensive | The history window or limit is too large | Start with seven days and one thread, then increase deliberately |

## Related documentation

- [Summary model providers](MODEL_PROVIDERS.md): all supported provider variables and
  hosted-provider examples.
- [Setup, scope, and storage](SETUP_AND_STORAGE.md): archive retention, reasoning policy,
  and what PostgreSQL stores.
- [Connect several computers with Tailscale](TAILSCALE_MULTI_MACHINE.md): central
  database, writer credentials, and source-machine setup.
- [Sync and worker operations](SYNC_OPERATIONS.md): resumable ingestion and unattended
  derived refreshes.
- [Security](../SECURITY.md): the network and credential boundary.
