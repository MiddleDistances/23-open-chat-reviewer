# Model providers

Summary cards are optional. The archive and all deterministic review features work
without a model. When enabled, a provider receives only a bounded, prompt-injection-aware
evidence packet and must return a JSON object that passes the `ResumeDraft` schema.

## Local Qwen (recommended)

Serve a Qwen instruct model with an OpenAI-compatible local server such as vLLM,
llama.cpp, Ollama, or LocalAI, then set:

```bash
export CHATREVIEW_SUMMARY_PROVIDER=openai-compatible
export CHATREVIEW_SUMMARY_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
export CHATREVIEW_SUMMARY_BASE_URL=http://127.0.0.1:8000/v1
```

The exact model is a deployment choice. Use a smaller instruct model when memory is
limited. Open Chat Reviewer does not start, stop, or assume ownership of your model
server.

## Hosted OpenAI-compatible services

All use `CHATREVIEW_SUMMARY_PROVIDER=openai-compatible` plus a model, base URL, and key.
The adapter requests strict JSON Schema first and falls back to JSON mode when a gateway
returns HTTP 400 or 422.

### Alibaba Cloud Model Studio

```bash
export CHATREVIEW_SUMMARY_MODEL=qwen-plus
export CHATREVIEW_SUMMARY_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
export CHATREVIEW_SUMMARY_API_KEY=replace-me
```

Model Studio URLs and model availability vary by region. Use the endpoint from the
[official base URL table](https://www.alibabacloud.com/help/en/model-studio/base-url).

### Hugging Face Inference Providers

```bash
export CHATREVIEW_SUMMARY_MODEL=YOUR-MODEL:preferred
export CHATREVIEW_SUMMARY_BASE_URL=https://router.huggingface.co/v1
export CHATREVIEW_SUMMARY_API_KEY=hf_replace_me
```

The OpenAI-compatible route is for chat completion models. See the
[Inference Providers documentation](https://huggingface.co/docs/inference-providers/en/index).

### OpenRouter

```bash
export CHATREVIEW_SUMMARY_MODEL=provider/model
export CHATREVIEW_SUMMARY_BASE_URL=https://openrouter.ai/api/v1
export CHATREVIEW_SUMMARY_API_KEY=replace-me
export CHATREVIEW_SUMMARY_HEADERS_JSON='{"HTTP-Referer":"https://your-project.example","X-OpenRouter-Title":"Open Chat Reviewer"}'
```

Attribution headers are optional. See the
[OpenRouter quickstart](https://openrouter.ai/docs/quickstart).

## OpenAI Responses API

Use the native Responses adapter for OpenAI API models, including compatible coding
models available to your API account:

```bash
export CHATREVIEW_SUMMARY_PROVIDER=openai-responses
export CHATREVIEW_SUMMARY_MODEL=YOUR-ACCOUNT-MODEL
export CHATREVIEW_SUMMARY_BASE_URL=https://api.openai.com/v1
export CHATREVIEW_SUMMARY_API_KEY=replace-me
```

The adapter sends `store: false` and requests a strict structured output. API keys and
model access are separate from a ChatGPT or coding-agent login; this project never reads
tokens from Codex or another source application. Confirm the model name using the
[OpenAI models API](https://platform.openai.com/docs/api-reference/models).

## Anthropic

```bash
export CHATREVIEW_SUMMARY_PROVIDER=anthropic
export CHATREVIEW_SUMMARY_MODEL=YOUR-CLAUDE-MODEL
export CHATREVIEW_SUMMARY_BASE_URL=https://api.anthropic.com
export CHATREVIEW_SUMMARY_API_KEY=replace-me
```

This adapter calls the native
[Messages API](https://platform.claude.com/docs/en/api/messages/create).

## Custom plugin

Implement the runtime-checkable protocol:

```python
class MyProvider:
    model_name = "my-provider/my-model"

    def generate_json(self, *, system_prompt, user_prompt, schema_name, schema):
        return {"concept": "..."}  # Return the complete schema-valid object.

    def close(self):
        pass

def build_provider():
    return MyProvider()
```

Then configure:

```bash
export CHATREVIEW_SUMMARY_PROVIDER=plugin
export CHATREVIEW_SUMMARY_PLUGIN=my_package.chatreview:build_provider
```

Install the plugin into the same uv environment. A plugin executes as trusted local code;
review it before installation.

## Shared settings

- `CHATREVIEW_SUMMARY_TIMEOUT` defaults to 600 seconds.
- `CHATREVIEW_SUMMARY_MAX_TOKENS` defaults to 1200.
- `CHATREVIEW_SUMMARY_HEADERS_JSON` adds string-valued request headers.
- `CHATREVIEW_ENABLE_SUMMARIES=1` enables summaries in the unattended worker.

Never commit keys. Put them in the mode-`0600`, Git-ignored
`.chatreview/archive.env`. Any hosted provider receives the selected chat excerpts, so
review that provider's retention and data-use terms before enabling it.
