"""Pluggable model providers for evidence-bounded conversation summaries.

The archive never gives a model database or filesystem access. Providers receive one
bounded prompt and return one JSON object. This keeps local Qwen, hosted OpenAI-style
gateways, Anthropic, and user-supplied adapters behind the same small interface.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit, urlunsplit


class SummaryProviderError(RuntimeError):
    """Raised when a configured summary provider cannot return valid JSON."""


@runtime_checkable
class SummaryProvider(Protocol):
    """Small provider interface used by the summarization module."""

    model_name: str

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class OpenAICompatibleProvider:
    """Chat Completions adapter for local and hosted OpenAI-compatible endpoints."""

    model_name: str
    base_url: str
    api_key: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = 600
    max_tokens: int = 1_200

    def __post_init__(self) -> None:
        self.base_url = _validated_base_url(self.base_url)
        self.max_tokens = max(256, int(self.max_tokens))

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model_name,
            "stream": False,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        try:
            response = _post_json(
                f"{self.base_url}/chat/completions",
                payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except SummaryProviderError as exc:
            # Some otherwise-compatible gateways implement JSON mode but not JSON Schema.
            if "HTTP 400" not in str(exc) and "HTTP 422" not in str(exc):
                raise
            payload["response_format"] = {"type": "json_object"}
            response = _post_json(
                f"{self.base_url}/chat/completions",
                payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SummaryProviderError("provider returned no assistant message") from exc
        return parse_json_object(content)

    def close(self) -> None:
        """HTTP requests are stateless, so there is no provider resource to release."""

    def _headers(self) -> dict[str, str]:
        result = dict(self.headers or {})
        if self.api_key:
            result.setdefault("Authorization", f"Bearer {self.api_key}")
        return result


@dataclass(slots=True)
class AnthropicProvider:
    """Native Anthropic Messages adapter."""

    model_name: str
    api_key: str
    base_url: str = "https://api.anthropic.com"
    api_version: str = "2023-06-01"
    timeout: float = 600
    max_tokens: int = 1_200

    def __post_init__(self) -> None:
        self.base_url = _validated_base_url(self.base_url)

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        schema_instruction = json.dumps(schema, separators=(",", ":"), ensure_ascii=False)
        payload = {
            "model": self.model_name,
            "max_tokens": max(256, int(self.max_tokens)),
            "temperature": 0,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\nReturn only one JSON object named {schema_name} "
                        f"that validates against this JSON Schema:\n{schema_instruction}"
                    ),
                }
            ],
        }
        response = _post_json(
            f"{self.base_url}/v1/messages",
            payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
            },
            timeout=self.timeout,
        )
        blocks = response.get("content", [])
        text = "\n".join(
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        if not text.strip():
            raise SummaryProviderError("Anthropic returned no text content")
        return parse_json_object(text)

    def close(self) -> None:
        """HTTP requests are stateless, so there is no provider resource to release."""


@dataclass(slots=True)
class OpenAIResponsesProvider:
    """Native Responses API adapter for OpenAI and Responses-compatible gateways."""

    model_name: str
    base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = 600
    max_tokens: int = 1_200

    def __post_init__(self) -> None:
        self.base_url = _validated_base_url(self.base_url)

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "model": self.model_name,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max(256, int(self.max_tokens)),
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = _post_json(
            f"{self.base_url}/responses",
            payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        text = response.get("output_text")
        if not text:
            text = "\n".join(
                str(block.get("text", ""))
                for item in response.get("output", [])
                if isinstance(item, dict)
                for block in item.get("content", [])
                if isinstance(block, dict) and block.get("type") == "output_text"
            )
        if not str(text or "").strip():
            raise SummaryProviderError("Responses API returned no output text")
        return parse_json_object(text)

    def close(self) -> None:
        """HTTP requests are stateless, so there is no provider resource to release."""

    def _headers(self) -> dict[str, str]:
        result = dict(self.headers or {})
        if self.api_key:
            result.setdefault("Authorization", f"Bearer {self.api_key}")
        return result


def provider_from_environment(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> SummaryProvider:
    """Build one provider from CLI overrides plus ``CHATREVIEW_SUMMARY_*`` settings."""

    kind = (provider or os.environ.get("CHATREVIEW_SUMMARY_PROVIDER", "")).strip().lower()
    if not kind:
        raise SummaryProviderError(
            "CHATREVIEW_SUMMARY_PROVIDER is not configured; choose openai-compatible, "
            "openai-responses, anthropic, or plugin"
        )
    resolved_model = (model_name or os.environ.get("CHATREVIEW_SUMMARY_MODEL", "")).strip()
    if not resolved_model and kind != "plugin":
        raise SummaryProviderError("CHATREVIEW_SUMMARY_MODEL is required")
    resolved_key = api_key if api_key is not None else os.environ.get("CHATREVIEW_SUMMARY_API_KEY")
    timeout = float(os.environ.get("CHATREVIEW_SUMMARY_TIMEOUT", "600"))
    max_tokens = int(os.environ.get("CHATREVIEW_SUMMARY_MAX_TOKENS", "1200"))

    if kind in {"openai", "openai-compatible", "local", "qwen"}:
        resolved_url = (
            base_url or os.environ.get("CHATREVIEW_SUMMARY_BASE_URL", "http://127.0.0.1:8000/v1")
        )
        raw_headers = os.environ.get("CHATREVIEW_SUMMARY_HEADERS_JSON", "{}").strip() or "{}"
        try:
            headers = json.loads(raw_headers)
        except json.JSONDecodeError as exc:
            raise SummaryProviderError("CHATREVIEW_SUMMARY_HEADERS_JSON must be valid JSON") from exc
        if not isinstance(headers, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()
        ):
            raise SummaryProviderError("CHATREVIEW_SUMMARY_HEADERS_JSON must be a string map")
        return OpenAICompatibleProvider(
            model_name=resolved_model,
            base_url=resolved_url,
            api_key=resolved_key,
            headers=headers,
            timeout=timeout,
            max_tokens=max_tokens,
        )

    if kind in {"openai-responses", "responses"}:
        resolved_url = base_url or os.environ.get(
            "CHATREVIEW_SUMMARY_BASE_URL", "https://api.openai.com/v1"
        )
        raw_headers = os.environ.get("CHATREVIEW_SUMMARY_HEADERS_JSON", "{}").strip() or "{}"
        try:
            headers = json.loads(raw_headers)
        except json.JSONDecodeError as exc:
            raise SummaryProviderError("CHATREVIEW_SUMMARY_HEADERS_JSON must be valid JSON") from exc
        if not isinstance(headers, dict) or any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()
        ):
            raise SummaryProviderError("CHATREVIEW_SUMMARY_HEADERS_JSON must be a string map")
        return OpenAIResponsesProvider(
            model_name=resolved_model,
            base_url=resolved_url,
            api_key=resolved_key,
            headers=headers,
            timeout=timeout,
            max_tokens=max_tokens,
        )

    if kind == "anthropic":
        if not resolved_key:
            raise SummaryProviderError("CHATREVIEW_SUMMARY_API_KEY is required for Anthropic")
        return AnthropicProvider(
            model_name=resolved_model,
            api_key=resolved_key,
            base_url=base_url
            or os.environ.get("CHATREVIEW_SUMMARY_BASE_URL", "https://api.anthropic.com"),
            api_version=os.environ.get("CHATREVIEW_ANTHROPIC_VERSION", "2023-06-01"),
            timeout=timeout,
            max_tokens=max_tokens,
        )

    if kind == "plugin":
        reference = os.environ.get("CHATREVIEW_SUMMARY_PLUGIN", "").strip()
        if not reference:
            raise SummaryProviderError("CHATREVIEW_SUMMARY_PLUGIN must be module:factory")
        return _load_plugin(reference)

    raise SummaryProviderError(f"unknown summary provider: {kind}")


def _load_plugin(reference: str) -> SummaryProvider:
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute:
        raise SummaryProviderError("summary plugin must use module:factory syntax")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
        candidate = factory()
    except Exception as exc:
        raise SummaryProviderError(f"could not load summary plugin {reference}: {exc}") from exc
    if not isinstance(candidate, SummaryProvider):
        raise SummaryProviderError(
            f"summary plugin {reference} does not implement model_name, generate_json, and close"
        )
    return candidate


def parse_json_object(value: Any) -> dict[str, Any]:
    """Extract one JSON object from plain or fenced provider output."""

    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise SummaryProviderError("provider response was not a JSON object") from exc
        try:
            result = json.loads(text[start : end + 1])
        except json.JSONDecodeError as nested:
            raise SummaryProviderError("provider response contained invalid JSON") from nested
    if not isinstance(result, dict):
        raise SummaryProviderError("provider response must be one JSON object")
    return result


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SummaryProviderError("summary provider base URL must use http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SummaryProviderError("summary provider base URL must not contain credentials or query data")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None,
    timeout: float,
) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=request_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read(2_000).decode(errors="replace")
        raise SummaryProviderError(f"provider HTTP {exc.code}: {detail}") from exc
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SummaryProviderError(f"provider request failed: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise SummaryProviderError("provider response body was not a JSON object")
    return data
