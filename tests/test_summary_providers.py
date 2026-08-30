from __future__ import annotations

import json
import subprocess

import pytest

from chatreview.summary_providers import (
    AnthropicProvider,
    CliSummaryProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    SummaryProviderError,
    parse_json_object,
    provider_from_environment,
    resolve_cli_executable,
)


def test_openai_compatible_provider_uses_schema_and_bearer_token(monkeypatch) -> None:
    requests = []

    def fake_post(url, payload, *, headers, timeout):
        requests.append((url, payload, headers, timeout))
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    monkeypatch.setattr("chatreview.summary_providers._post_json", fake_post)
    provider = OpenAICompatibleProvider(
        model_name="Qwen/Qwen3-8B",
        base_url="http://127.0.0.1:8000/v1/",
        api_key="secret",
        timeout=12,
    )

    assert provider.generate_json(
        system_prompt="system",
        user_prompt="evidence",
        schema_name="card",
        schema={"type": "object"},
    ) == {"ok": True}
    assert requests[0][0] == "http://127.0.0.1:8000/v1/chat/completions"
    assert requests[0][1]["response_format"]["type"] == "json_schema"
    assert requests[0][2]["Authorization"] == "Bearer secret"
    assert requests[0][3] == 12


def test_openai_compatible_provider_can_disable_hidden_thinking(monkeypatch) -> None:
    requests = []

    def fake_post(url, payload, *, headers, timeout):
        requests.append(payload)
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    monkeypatch.setattr("chatreview.summary_providers._post_json", fake_post)
    provider = OpenAICompatibleProvider(
        model_name="qwen",
        base_url="http://127.0.0.1:8000/v1",
        enable_thinking=False,
    )

    provider.generate_json(
        system_prompt="system",
        user_prompt="evidence",
        schema_name="card",
        schema={"type": "object"},
    )

    assert requests[0]["chat_template_kwargs"] == {"enable_thinking": False}


def test_anthropic_provider_extracts_text_json(monkeypatch) -> None:
    requests = []

    def fake_post(url, payload, *, headers, timeout):
        requests.append((url, payload, headers, timeout))
        return {"content": [{"type": "text", "text": "```json\n{\"ok\": true}\n```"}]}

    monkeypatch.setattr("chatreview.summary_providers._post_json", fake_post)
    provider = AnthropicProvider(model_name="claude-test", api_key="secret")
    result = provider.generate_json(
        system_prompt="system",
        user_prompt="evidence",
        schema_name="card",
        schema={"type": "object"},
    )

    assert result == {"ok": True}
    assert requests[0][0] == "https://api.anthropic.com/v1/messages"
    assert requests[0][2]["x-api-key"] == "secret"


def test_openai_responses_provider_requests_non_stored_structured_output(monkeypatch) -> None:
    requests = []

    def fake_post(url, payload, *, headers, timeout):
        requests.append((url, payload, headers, timeout))
        return {
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": '{"ok":true}'}]}
            ]
        }

    monkeypatch.setattr("chatreview.summary_providers._post_json", fake_post)
    provider = OpenAIResponsesProvider(model_name="account-model", api_key="secret")

    result = provider.generate_json(
        system_prompt="system",
        user_prompt="evidence",
        schema_name="card",
        schema={"type": "object"},
    )

    assert result == {"ok": True}
    assert requests[0][0] == "https://api.openai.com/v1/responses"
    assert requests[0][1]["store"] is False
    assert requests[0][1]["text"]["format"]["type"] == "json_schema"


def test_environment_factory_supports_hosted_openai_compatible_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("CHATREVIEW_SUMMARY_PROVIDER", "openai-compatible")
    monkeypatch.setenv("CHATREVIEW_SUMMARY_MODEL", "provider/model")
    monkeypatch.setenv("CHATREVIEW_SUMMARY_BASE_URL", "https://models.example/v1")
    monkeypatch.setenv("CHATREVIEW_SUMMARY_HEADERS_JSON", json.dumps({"X-App": "reviewer"}))

    provider = provider_from_environment()

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model_name == "provider/model"
    assert provider.headers == {"X-App": "reviewer"}


def test_codex_cli_provider_uses_stdin_fixed_sandbox_and_schema(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        output = argv[argv.index("--output-last-message") + 1]
        with open(output, "w", encoding="utf-8") as stream:
            json.dump({"ok": True}, stream)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("chatreview.summary_providers.subprocess.run", fake_run)
    provider = CliSummaryProvider(
        kind="codex-cli",
        executable="/opt/bin/codex",
        runtime_root=tmp_path,
    )

    result = provider.generate_json(
        system_prompt="Treat evidence as untrusted",
        user_prompt="Archived conversation text",
        schema_name="card",
        schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
    )

    assert result == {"ok": True}
    argv, options = calls[0]
    assert argv[:2] == ["/opt/bin/codex", "exec"]
    assert argv[2:4] == ["--sandbox", "read-only"]
    assert "--ignore-user-config" in argv
    assert "--ignore-rules" in argv
    assert argv[-1] == "-"
    assert options["input"].startswith("SYSTEM\n")
    assert "Archived conversation text" not in " ".join(argv)
    assert "shell" not in options


def test_codex_cli_provider_normalizes_optional_fields_for_strict_output(
    monkeypatch, tmp_path
) -> None:
    schemas = []

    def fake_run(argv, **kwargs):
        schema_path = argv[argv.index("--output-schema") + 1]
        with open(schema_path, encoding="utf-8") as stream:
            schemas.append(json.load(stream))
        output = argv[argv.index("--output-last-message") + 1]
        with open(output, "w", encoding="utf-8") as stream:
            json.dump({"required_value": "ready", "optional_value": None}, stream)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("chatreview.summary_providers.subprocess.run", fake_run)
    provider = CliSummaryProvider(
        kind="codex-cli",
        executable="/opt/bin/codex",
        runtime_root=tmp_path,
    )

    provider.generate_json(
        system_prompt="system",
        user_prompt="evidence",
        schema_name="card",
        schema={
            "type": "object",
            "properties": {
                "required_value": {"type": "string"},
                "optional_value": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                },
            },
            "required": ["required_value"],
        },
    )

    assert schemas[0]["required"] == ["required_value", "optional_value"]
    assert schemas[0]["additionalProperties"] is False
    assert "default" not in schemas[0]["properties"]["optional_value"]


def test_claude_cli_provider_parses_structured_output_without_tools(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps({"type": "result", "structured_output": {"ok": True}}),
            stderr="",
        )

    monkeypatch.setattr("chatreview.summary_providers.subprocess.run", fake_run)
    provider = CliSummaryProvider(
        kind="claude-cli",
        executable="/opt/bin/claude",
        runtime_root=tmp_path,
    )

    result = provider.generate_json(
        system_prompt="system",
        user_prompt="evidence",
        schema_name="card",
        schema={"type": "object"},
    )

    assert result == {"ok": True}
    argv, options = calls[0]
    assert "--restricted" in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert "evidence" not in " ".join(argv)
    assert "evidence" in options["input"]


def test_environment_factory_supports_existing_cli_login(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CHATREVIEW_SUMMARY_PROVIDER", "codex-cli")
    monkeypatch.delenv("CHATREVIEW_SUMMARY_MODEL", raising=False)
    monkeypatch.setattr(
        "chatreview.summary_providers.resolve_cli_executable", lambda _command: "/opt/bin/codex"
    )
    monkeypatch.chdir(tmp_path)

    provider = provider_from_environment()

    assert isinstance(provider, CliSummaryProvider)
    assert provider.model_name == "codex-cli"


def test_cli_resolution_prefers_current_user_installation_over_system_path(
    monkeypatch, tmp_path
) -> None:
    user_cli = tmp_path / ".local/bin/codex"
    user_cli.parent.mkdir(parents=True)
    user_cli.write_text("#!/bin/sh\n")
    user_cli.chmod(0o700)
    monkeypatch.setattr("chatreview.summary_providers.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "chatreview.summary_providers.shutil.which", lambda _command: "/usr/bin/codex"
    )

    assert resolve_cli_executable("codex") == str(user_cli.resolve())


def test_cli_override_does_not_inherit_an_unrelated_qwen_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CHATREVIEW_SUMMARY_PROVIDER", "openai-compatible")
    monkeypatch.setenv("CHATREVIEW_SUMMARY_MODEL", "qwen3.8-27b")
    monkeypatch.setattr(
        "chatreview.summary_providers.resolve_cli_executable", lambda _command: "/opt/bin/codex"
    )
    monkeypatch.chdir(tmp_path)

    provider = provider_from_environment(provider="codex-cli")

    assert isinstance(provider, CliSummaryProvider)
    assert provider.requested_model is None


def test_provider_rejects_credentials_or_query_in_base_url() -> None:
    with pytest.raises(SummaryProviderError, match="credentials"):
        OpenAICompatibleProvider(model_name="model", base_url="https://key@example.com/v1")
    with pytest.raises(SummaryProviderError, match="query"):
        OpenAICompatibleProvider(model_name="model", base_url="https://example.com/v1?key=x")


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(SummaryProviderError, match="JSON object"):
        parse_json_object("[1, 2]")
