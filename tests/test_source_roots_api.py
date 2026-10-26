from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from chatreview.api import create_app
from chatreview.source_roots import load_source_roots, save_source_roots, source_roots_path


def _make_provider_roots(tmp_path: Path) -> dict[str, list[Path]]:
    root_base = tmp_path / "configured-roots"
    roots = {
        "codex": [root_base / "codex-primary", root_base / "codex-secondary"],
        "claude": [root_base / "claude"],
        "gemini": [root_base / "gemini"],
        "opencode": [root_base / "opencode"],
        "git": [root_base / "repositories"],
    }
    for provider_roots in roots.values():
        for root in provider_roots:
            root.mkdir(parents=True)
    return roots


def _flat_roots(roots: dict[str, list[Path]]) -> list[dict[str, str]]:
    return [
        {"provider": provider, "path": str(root)}
        for provider, provider_roots in roots.items()
        for root in provider_roots
    ]


def test_setup_status_reports_all_machine_roots_and_source_action_metadata(
    corpus, tmp_path: Path
) -> None:
    settings, _, _ = corpus
    roots = _make_provider_roots(tmp_path)
    save_source_roots(
        settings.data_dir,
        {provider: [str(root) for root in provider_roots] for provider, provider_roots in roots.items()},
    )

    client = TestClient(create_app(settings), client=("127.0.0.1", 45123))
    response = client.get("/api/setup/status")

    assert response.status_code == 200
    payload = response.json()
    assert {
        (root["provider"], root["path"])
        for root in payload["roots"]
    } == {
        (provider, str(root.resolve()))
        for provider, provider_roots in roots.items()
        for root in provider_roots
    }
    assert payload["source_actions_enabled"] is True
    assert "available" in payload["source_actions_message"].lower()
    assert payload["source_runtime_file"] == "source-roots.json"


def test_local_source_update_persists_multiple_roots_without_restart_or_archive_env_change(
    corpus, tmp_path: Path
) -> None:
    settings, _, _ = corpus
    roots = _make_provider_roots(tmp_path)
    archive_env = settings.data_dir / "archive.env"
    archive_env.parent.mkdir(parents=True, exist_ok=True)
    archive_before = "export CHATREVIEW_DATABASE_URL='postgresql://archive:secret@db/chatreview'\n"
    archive_env.write_text(archive_before, encoding="utf-8")

    client = TestClient(create_app(settings), client=("127.0.0.1", 45123))
    response = client.put("/api/setup/sources", json={"roots": _flat_roots(roots)})

    assert response.status_code == 200
    expected = {
        provider: [str(root.resolve()) for root in provider_roots]
        for provider, provider_roots in roots.items()
    }
    saved_path = source_roots_path(settings.data_dir)
    assert json.loads(saved_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "roots": expected,
    }
    assert load_source_roots(settings.data_dir) == expected
    assert archive_env.read_text(encoding="utf-8") == archive_before

    # The same app instance observes the new machine-local configuration.
    status = client.get("/api/setup/status")
    assert status.status_code == 200
    assert [root["path"] for root in status.json()["roots"]] == [
        path
        for provider in ("codex", "claude", "gemini", "opencode", "git")
        for path in expected[provider]
    ]
    assert status.json()["source_actions_enabled"] is True


def test_source_update_rejects_invalid_provider_blank_path_and_extra_fields(corpus) -> None:
    settings, _, _ = corpus
    client = TestClient(create_app(settings), client=("127.0.0.1", 45123))

    invalid_payloads = (
        {"roots": [{"provider": "openai", "path": "/tmp/codex"}]},
        {"roots": [{"provider": "codex", "path": ""}]},
        {"roots": [{"provider": "codex", "path": "   "}]},
        {"roots": [{"provider": "codex", "path": "/tmp/codex", "label": "extra"}]},
        {"roots": [{"provider": "codex", "path": "/tmp/codex"}], "unexpected": True},
    )

    for payload in invalid_payloads:
        response = client.put("/api/setup/sources", json=payload)
        assert response.status_code == 422, payload


def test_remote_source_update_requires_explicit_private_opt_in(corpus, monkeypatch, tmp_path: Path) -> None:
    settings, _, _ = corpus
    roots = _make_provider_roots(tmp_path)
    payload = {"roots": _flat_roots(roots)}
    client = TestClient(create_app(settings), client=("100.101.102.103", 45123))
    monkeypatch.delenv("CHATREVIEW_ALLOW_REMOTE_SOURCE_SETUP", raising=False)

    denied = client.put("/api/setup/sources", json=payload)

    assert denied.status_code == 403
    assert not source_roots_path(settings.data_dir).exists()

    monkeypatch.setenv("CHATREVIEW_ALLOW_REMOTE_SOURCE_SETUP", "1")
    allowed = client.put("/api/setup/sources", json=payload)

    assert allowed.status_code == 200
    assert allowed.json()["source_actions_enabled"] is True
    assert load_source_roots(settings.data_dir) is not None
