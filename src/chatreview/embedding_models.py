"""Allowlisted local embedding-model downloads for the setup UI.

The browser selects a fixed preset identifier; it never supplies a repository,
revision, cache path, or Hugging Face credential.  Downloads use the standard
Hugging Face cache so SentenceTransformers can reuse an existing local copy.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from chatreview.semantic import DEFAULT_MODEL, DEFAULT_MODEL_REVISION

EmbeddingModelState = Literal[
    "ready", "not_downloaded", "queued", "downloading", "failed", "interrupted", "unavailable"
]
DEFAULT_EMBEDDING_PRESET = "qwen3-embedding-0.6b"
STATE_FILE = "embedding-model-download.json"
ACTIVE_STATES = frozenset({"queued", "downloading"})


class EmbeddingModelError(RuntimeError):
    """Base error safe to expose through the setup API."""


class UnknownEmbeddingPreset(EmbeddingModelError):
    """Raised when a browser requests a preset outside the fixed catalog."""


class EmbeddingModelDownloadActive(EmbeddingModelError):
    """Raised when this process is already downloading an embedding model."""


class EmbeddingModelDependencyMissing(EmbeddingModelError):
    """Raised when the optional semantic dependencies are not installed."""


@dataclass(frozen=True, slots=True)
class EmbeddingModelPreset:
    """One reviewed embedding configuration exposed to the browser."""

    id: str
    label: str
    description: str
    model_name: str
    revision: str
    dimensions: int
    source_url: str


PRESETS = {
    DEFAULT_EMBEDDING_PRESET: EmbeddingModelPreset(
        id=DEFAULT_EMBEDDING_PRESET,
        label="Balanced local (recommended)",
        description="Qwen3 0.6B at 512 dimensions; private, multilingual semantic search.",
        model_name=DEFAULT_MODEL,
        revision=DEFAULT_MODEL_REVISION,
        dimensions=512,
        source_url="https://huggingface.co/Qwen/Qwen3-Embedding-0.6B",
    )
}

CacheProbe = Callable[[EmbeddingModelPreset], bool]
Downloader = Callable[[EmbeddingModelPreset], None]


class EmbeddingModelManager:
    """Report local model availability and own one resumable background download."""

    def __init__(
        self,
        data_dir: Path,
        *,
        cache_probe: CacheProbe | None = None,
        downloader: Downloader | None = None,
        state_path: Path | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state_path = state_path or self.data_dir / STATE_FILE
        self.cache_probe = cache_probe or _is_cached
        self.downloader = downloader or _download
        self._mutex = threading.RLock()
        self._thread: threading.Thread | None = None

    def catalog(self) -> list[dict[str, Any]]:
        """Return public, path-free status for every allowlisted preset."""

        with self._mutex:
            state = self._read()
            if state and state.get("status") in ACTIVE_STATES:
                owner_pid = _integer(state.get("owner_pid"))
                if owner_pid and owner_pid != os.getpid() and not _pid_alive(owner_pid):
                    state.update(
                        status="interrupted",
                        message="The web process stopped before the model download finished",
                        error=None,
                        owner_pid=None,
                        updated_at=_now(),
                        finished_at=_now(),
                    )
                    self._write(state)
            return [self._public_model(preset, state) for preset in PRESETS.values()]

    def start(self, preset_id: str) -> dict[str, Any]:
        """Queue an allowlisted Hugging Face snapshot download and return immediately."""

        preset = PRESETS.get(preset_id)
        if preset is None:
            raise UnknownEmbeddingPreset("unknown embedding model preset")
        with self._mutex:
            current = self.catalog()
            selected = next(item for item in current if item["id"] == preset_id)
            if selected["status"] == "ready":
                return selected
            if any(item["status"] in ACTIVE_STATES for item in current):
                raise EmbeddingModelDownloadActive("an embedding model download is already running")
            if selected["status"] == "unavailable":
                raise EmbeddingModelDependencyMissing(
                    "install the semantic dependencies with `uv sync --extra semantic` first"
                )
            now = _now()
            state = {
                "preset_id": preset.id,
                "status": "queued",
                "message": "Embedding model download queued",
                "error": None,
                "owner_pid": os.getpid(),
                "started_at": now,
                "updated_at": now,
                "finished_at": None,
            }
            self._write(state)
            self._thread = threading.Thread(
                target=self._run,
                args=(preset,),
                name=f"chatreview-model-{preset.id}",
                daemon=True,
            )
            self._thread.start()
            return self._public_model(preset, state)

    def wait(self, timeout: float | None = None) -> list[dict[str, Any]]:
        """Wait for the current in-process download; useful for tests and checks."""

        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.catalog()

    def _run(self, preset: EmbeddingModelPreset) -> None:
        state = self._read() or {"preset_id": preset.id}
        try:
            state.update(
                status="downloading",
                message="Downloading the pinned model files from Hugging Face",
                updated_at=_now(),
            )
            self._write(state)
            self.downloader(preset)
            if not self.cache_probe(preset):
                raise EmbeddingModelError("the download finished without a usable cached snapshot")
            state.update(status="ready", message="Embedding model is ready on this machine", error=None)
        except BaseException as exc:
            state.update(
                status="failed",
                message="Embedding model download failed",
                error=_safe_message(exc),
            )
        finally:
            state.update(owner_pid=None, updated_at=_now(), finished_at=_now())
            self._write(state)

    def _public_model(
        self,
        preset: EmbeddingModelPreset,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        dependency_available = _dependency_available()
        cached = dependency_available and self.cache_probe(preset)
        relevant = state if state and state.get("preset_id") == preset.id else None
        if cached:
            status: EmbeddingModelState = "ready"
            message = "Already downloaded on this machine"
            error = None
        elif not dependency_available:
            status = "unavailable"
            message = "Install the optional semantic dependencies before downloading"
            error = None
        elif relevant and relevant.get("status") in {
            "queued",
            "downloading",
            "failed",
            "interrupted",
        }:
            status = relevant["status"]
            message = str(relevant.get("message") or "")
            error = relevant.get("error")
        else:
            status = "not_downloaded"
            message = "Not downloaded on this machine"
            error = None
        return {
            "id": preset.id,
            "label": preset.label,
            "description": preset.description,
            "model_name": preset.model_name,
            "revision": preset.revision,
            "dimensions": preset.dimensions,
            "source_url": preset.source_url,
            "status": status,
            "message": message,
            "error": error,
        }

    def _read(self) -> dict[str, Any] | None:
        try:
            value = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _write(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True))
        with suppress(OSError):
            temporary.chmod(0o600)
        temporary.replace(self.state_path)


def embedding_preset(preset_id: str) -> EmbeddingModelPreset:
    """Resolve a fixed preset for setup/build command construction."""

    try:
        return PRESETS[preset_id]
    except KeyError as exc:
        raise UnknownEmbeddingPreset("unknown embedding model preset") from exc


def _dependency_available() -> bool:
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        return False
    return True


def _is_cached(preset: EmbeddingModelPreset) -> bool:
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError:
        return False
    try:
        snapshot_download(
            repo_id=preset.model_name,
            revision=preset.revision,
            local_files_only=True,
        )
    except (LocalEntryNotFoundError, OSError, ValueError):
        return False
    return True


def _download(preset: EmbeddingModelPreset) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise EmbeddingModelDependencyMissing(
            "install the semantic dependencies with `uv sync --extra semantic` first"
        ) from exc
    snapshot_download(repo_id=preset.model_name, revision=preset.revision)


def _safe_message(value: object) -> str:
    message = str(value).strip() or type(value).__name__
    return message[:2_000]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True
