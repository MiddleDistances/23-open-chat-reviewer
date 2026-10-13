from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chatreview.api import create_app
from chatreview.summary_jobs import summary_agent_catalog
from chatreview.summary_providers import OpenAICompatibleProvider, provider_from_environment
from chatreview.summary_setup import (
    SummaryConfigurationError,
    normalize_base_url,
    probe_openai_compatible,
    save_runtime_configuration,
)


class _Response:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, *, timeout: float):
        self.request = request
        self.timeout = timeout
        return self.response


def test_runtime_configuration_is_private_and_catalog_reads_it(tmp_path: Path, monkeypatch) -> None:
    archive = tmp_path / "archive.env"
    archive.write_text(
        "export CHATREVIEW_DATABASE_URL='postgresql://user:secret@db/archive'\n"
        "export UNRELATED_SECRET='must-stay'\n",
        encoding="utf-8",
    )

    saved = save_runtime_configuration(
        tmp_path,
        provider="qwen",
        model="qwen3.8-27b",
        base_url="http://127.0.0.1:18000/v1/",
        disable_thinking=True,
    )

    runtime = tmp_path / "summary-provider.json"
    assert saved.provider == "openai-compatible"
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o600
    assert json.loads(runtime.read_text(encoding="utf-8")) == {
        "base_url": "http://127.0.0.1:18000/v1",
        "disable_thinking": True,
        "model": "qwen3.8-27b",
        "provider": "openai-compatible",
        "updated_at": saved.updated_at,
    }
    assert "secret" not in runtime.read_text(encoding="utf-8")
    assert "must-stay" in archive.read_text(encoding="utf-8")

    monkeypatch.setenv("CHATREVIEW_SUMMARY_PROVIDER", "qwen")
    monkeypatch.setenv("CHATREVIEW_SUMMARY_MODEL", "old-model")
    monkeypatch.setenv("CHATREVIEW_SUMMARY_BASE_URL", "http://127.0.0.1:8000/v1")
    provider = provider_from_environment(provider="qwen", config_dir=tmp_path)
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model_name == "qwen3.8-27b"
    assert provider.base_url == "http://127.0.0.1:18000/v1"
    assert provider.enable_thinking is False
    assert summary_agent_catalog(tmp_path)[0]["installed"] is True


def test_runtime_endpoint_precedes_stale_environment_provider(tmp_path: Path, monkeypatch) -> None:
    save_runtime_configuration(
        tmp_path,
        provider="qwen",
        model="runtime-model",
        base_url="http://127.0.0.1:18000/v1",
        disable_thinking=True,
    )
    monkeypatch.setenv("CHATREVIEW_SUMMARY_PROVIDER", "codex-cli")

    provider = provider_from_environment(config_dir=tmp_path)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model_name == "runtime-model"


def test_broken_endpoint_file_does_not_block_explicit_cli(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "summary-provider.json").write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(
        "chatreview.summary_providers.resolve_cli_executable", lambda _command: "/opt/bin/codex"
    )

    provider = provider_from_environment(provider="codex-cli", config_dir=tmp_path)

    assert provider.model_name == "codex-cli"


def test_probe_returns_models_and_never_sends_a_key_unless_explicit(tmp_path, monkeypatch) -> None:
    opener = _Opener(_Response(b'{"object":"list","data":[{"id":"qwen3.8-27b"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )

    result = probe_openai_compatible(
        "http://127.0.0.1:18000/v1/",
        model="qwen3.8-27b",
    )

    assert result.ok is True
    assert result.stage == "ready"
    assert result.models == ("qwen3.8-27b",)
    assert result.model_available is True
    assert opener.request.full_url == "http://127.0.0.1:18000/v1/models"
    assert "Authorization" not in opener.request.headers
    assert result.to_dict()["checks"][-1]["id"] == "model"


def test_probe_rejects_public_http_and_redirects_are_not_followed(monkeypatch) -> None:
    monkeypatch.setattr(
        "chatreview.summary_setup.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("8.8.8.8", 80))],
    )
    public_http = probe_openai_compatible("http://8.8.8.8:80/v1")
    assert public_http.ok is False
    assert public_http.stage == "network"
    assert "https" in public_http.message

    with pytest.raises(SummaryConfigurationError, match="credentials"):
        normalize_base_url("http://secret@example.com/v1")


def test_probe_reports_missing_selected_model(monkeypatch) -> None:
    opener = _Opener(_Response(b'{"data":[{"id":"other-model"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )
    result = probe_openai_compatible("http://127.0.0.1:8000/v1", model="missing-model")
    assert result.ok is False
    assert result.stage == "model"
    assert result.model_available is False


def test_summary_configuration_api_is_local_only_and_runtime_backed(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    archive = settings.data_dir / "archive.env"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        "export CHATREVIEW_DATABASE_URL='postgresql://user:secret@db/archive'\n"
        "export UNRELATED_SECRET='must-stay'\n",
        encoding="utf-8",
    )
    opener = _Opener(_Response(b'{"data":[{"id":"qwen3.8-27b"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )

    app = create_app(settings)
    local_client = TestClient(app, client=("127.0.0.1", 45123))
    before = local_client.get("/api/summary-agent/configuration")
    assert before.status_code == 200
    assert before.json()["actions_enabled"] is True
    assert before.json()["configured"] is False

    probe = local_client.post(
        "/api/summary-agent/probe",
        json={"base_url": "http://127.0.0.1:18000/v1", "model": "qwen3.8-27b"},
    )
    assert probe.status_code == 200
    assert probe.json()["ok"] is True
    assert "Authorization" not in opener.request.headers

    saved = local_client.put(
        "/api/summary-agent/configuration",
        json={
            "provider": "qwen",
            "model": "qwen3.8-27b",
            "base_url": "http://127.0.0.1:18000/v1",
            "disable_thinking": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["source"] == "runtime"
    assert saved.json()["api_key_configured"] is False
    assert "secret" not in saved.text
    assert "must-stay" in archive.read_text(encoding="utf-8")
    assert local_client.get("/api/summary-agent/configuration").json()["model"] == "qwen3.8-27b"

    remote_client = TestClient(app, client=("100.101.102.103", 45123))
    denied = remote_client.put(
        "/api/summary-agent/configuration",
        json={
            "provider": "qwen",
            "model": "other",
            "base_url": "http://127.0.0.1:8000/v1",
        },
    )
    assert denied.status_code == 403


def test_probe_reuses_existing_key_only_for_the_configured_endpoint(corpus, monkeypatch) -> None:
    settings, _, _ = corpus
    save_runtime_configuration(
        settings.data_dir,
        provider="qwen",
        model="qwen3.8-27b",
        base_url="http://127.0.0.1:18000/v1",
        disable_thinking=True,
    )
    monkeypatch.setenv("CHATREVIEW_SUMMARY_API_KEY", "server-owned-key")
    opener = _Opener(_Response(b'{"data":[{"id":"qwen3.8-27b"}]}'))
    monkeypatch.setattr(
        "chatreview.summary_setup.urllib.request.build_opener",
        lambda *_handlers: opener,
    )
    client = TestClient(create_app(settings), client=("127.0.0.1", 45123))

    response = client.post(
        "/api/summary-agent/probe",
        json={"base_url": "http://127.0.0.1:18000/v1", "model": "qwen3.8-27b"},
    )

    assert response.status_code == 200
    assert opener.request.headers["Authorization"] == "Bearer server-owned-key"

    other = client.post(
        "/api/summary-agent/probe",
        json={"base_url": "http://127.0.0.1:18001/v1", "model": "qwen3.8-27b"},
    )
    assert other.status_code == 200
    assert "Authorization" not in opener.request.headers


def test_configuration_api_refuses_unsafe_destination_before_saving(corpus) -> None:
    settings, _, _ = corpus
    client = TestClient(create_app(settings), client=("127.0.0.1", 45123))

    response = client.put(
        "/api/summary-agent/configuration",
        json={
            "provider": "qwen",
            "model": "metadata-model",
            "base_url": "http://169.254.169.254/v1",
            "disable_thinking": True,
        },
    )

    assert response.status_code == 422
    assert "not saved" in response.json()["detail"]
    assert not (settings.data_dir / "summary-provider.json").exists()
