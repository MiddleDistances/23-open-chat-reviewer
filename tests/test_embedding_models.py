from __future__ import annotations

from pathlib import Path

import pytest

from chatreview.embedding_models import (
    DEFAULT_EMBEDDING_PRESET,
    EmbeddingModelManager,
    UnknownEmbeddingPreset,
)


def test_embedding_model_download_moves_from_missing_to_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached = False

    def cache_probe(_preset) -> bool:
        return cached

    def download(_preset) -> None:
        nonlocal cached
        cached = True

    monkeypatch.setattr("chatreview.embedding_models._dependency_available", lambda: True)
    manager = EmbeddingModelManager(
        tmp_path,
        cache_probe=cache_probe,
        downloader=download,
    )

    assert manager.catalog()[0]["status"] == "not_downloaded"
    manager.start(DEFAULT_EMBEDDING_PRESET)
    model = manager.wait(timeout=2)[0]

    assert model["status"] == "ready"
    assert model["model_name"] == "Qwen/Qwen3-Embedding-0.6B"
    assert model["dimensions"] == 512
    assert "path" not in model


def test_embedding_model_download_rejects_unknown_browser_repository(tmp_path: Path) -> None:
    manager = EmbeddingModelManager(tmp_path, cache_probe=lambda _preset: False)

    with pytest.raises(UnknownEmbeddingPreset, match="unknown embedding model preset"):
        manager.start("arbitrary/user-supplied-model")
