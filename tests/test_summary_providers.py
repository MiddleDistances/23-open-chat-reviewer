from __future__ import annotations

import json

import pytest

from chatreview.summary_providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    SummaryProviderError,
    parse_json_object,
    provider_from_environment,
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


def test_provider_rejects_credentials_or_query_in_base_url() -> None:
    with pytest.raises(SummaryProviderError, match="credentials"):
        OpenAICompatibleProvider(model_name="model", base_url="https://key@example.com/v1")
    with pytest.raises(SummaryProviderError, match="query"):
        OpenAICompatibleProvider(model_name="model", base_url="https://example.com/v1?key=x")


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(SummaryProviderError, match="JSON object"):
        parse_json_object("[1, 2]")
