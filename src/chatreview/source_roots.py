"""Machine-local configuration for archive source roots.

Source roots describe where one machine keeps its read-only conversation and Git
inputs.  They belong to the machine running the sync process and are therefore
stored beside the other local runtime state, not in the shared archive database.

The file format is intentionally small and credential-free::

    {
      "version": 1,
      "roots": {
        "codex": ["/home/user/.codex"],
        "claude": [],
        "gemini": ["/home/user/.gemini"],
        "git": ["/home/user/Projects"]
      }
    }

Every path is canonicalized before it is persisted.  This makes a configuration
with multiple aliases for the same directory deterministic and lets callers use
the same normalized mapping for adapter construction and setup previews.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

SOURCE_ROOTS_FILENAME = "source-roots.json"
SOURCE_ROOTS_VERSION = 1
SUPPORTED_PROVIDERS = ("codex", "claude", "gemini", "opencode", "git")
SUPPORTED_PROVIDER_SET = frozenset(SUPPORTED_PROVIDERS)
MAX_ROOTS_PER_PROVIDER = 16
MAX_ROOT_PATH_LENGTH = 4_096

type SourceRoots = dict[str, list[str]]
type SourceRootRecord = dict[str, str]


class SourceRootConfigurationError(ValueError):
    """Raised when machine-local source-root configuration is unsafe or invalid."""


def source_roots_path(data_dir: Path | str) -> Path:
    """Return the source-root configuration path below a runtime data directory.

    ``data_dir`` is the existing machine-local ``.chatreview`` directory, in
    the same way that the summary runtime configuration receives its data
    directory.  The directory itself is not created by this helper.
    """

    return Path(data_dir).expanduser() / SOURCE_ROOTS_FILENAME


def normalize_source_path(value: str) -> str:
    """Validate and canonicalize one configured source path."""

    if not isinstance(value, str):
        raise SourceRootConfigurationError("source root path must be a string")
    if len(value) > MAX_ROOT_PATH_LENGTH:
        raise SourceRootConfigurationError(
            f"source root path must be at most {MAX_ROOT_PATH_LENGTH} characters"
        )
    if "\x00" in value:
        raise SourceRootConfigurationError("source root path must not contain NUL")
    candidate = value.strip()
    if not candidate:
        raise SourceRootConfigurationError("source root path must not be blank")
    try:
        normalized = Path(candidate).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SourceRootConfigurationError("source root path could not be resolved") from exc
    normalized_text = str(normalized)
    if len(normalized_text) > MAX_ROOT_PATH_LENGTH:
        raise SourceRootConfigurationError(
            f"source root path must be at most {MAX_ROOT_PATH_LENGTH} characters"
        )
    return normalized_text


def normalize_source_roots(roots: Mapping[str, Sequence[str]]) -> SourceRoots:
    """Validate and normalize a provider-to-path mapping.

    The returned mapping always contains every supported provider in stable
    order.  Missing providers are represented by empty lists, while explicitly
    supplied empty lists remain empty.  Paths are deduplicated after
    ``expanduser().resolve(strict=False)`` and retain their first-seen order.
    """

    if not isinstance(roots, Mapping):
        raise SourceRootConfigurationError("source roots must be an object")
    _validate_provider_keys(roots)
    normalized: SourceRoots = {provider: [] for provider in SUPPORTED_PROVIDERS}
    for provider, values in roots.items():
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            raise SourceRootConfigurationError(
                f"source roots for {provider} must be a list of paths"
            )
        paths: list[str] = []
        seen: set[str] = set()
        for value in values:
            path = normalize_source_path(value)
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
        if len(paths) > MAX_ROOTS_PER_PROVIDER:
            raise SourceRootConfigurationError(
                f"source roots for {provider} may contain at most {MAX_ROOTS_PER_PROVIDER} paths"
            )
        normalized[provider] = paths
    return normalized


def source_roots_from_flat_records(records: Iterable[Mapping[str, Any]]) -> SourceRoots:
    """Convert ``[{"provider": ..., "path": ...}]`` records to a full mapping."""

    if isinstance(records, (str, bytes, bytearray)):
        raise SourceRootConfigurationError("source-root records must be a list")
    grouped: SourceRoots = {provider: [] for provider in SUPPORTED_PROVIDERS}
    try:
        iterator = iter(records)
    except TypeError as exc:
        raise SourceRootConfigurationError("source-root records must be a list") from exc
    for record in iterator:
        if not isinstance(record, Mapping):
            raise SourceRootConfigurationError("each source-root record must be an object")
        if "provider" not in record or "path" not in record:
            raise SourceRootConfigurationError("each source-root record needs provider and path")
        provider = record["provider"]
        if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDER_SET:
            raise SourceRootConfigurationError(f"unsupported source-root provider: {provider!r}")
        grouped[provider].append(record["path"])
    return normalize_source_roots(grouped)


def source_roots_to_flat_records(roots: Mapping[str, Sequence[str]]) -> list[SourceRootRecord]:
    """Convert a provider mapping to ordered ``{"provider", "path"}`` records."""

    normalized = normalize_source_roots(roots)
    return [
        {"provider": provider, "path": path}
        for provider in SUPPORTED_PROVIDERS
        for path in normalized[provider]
    ]


# Short aliases make the conversion seam discoverable without duplicating logic.
records_to_source_roots = source_roots_from_flat_records
source_roots_to_records = source_roots_to_flat_records


def load_source_roots(data_dir: Path | str) -> SourceRoots | None:
    """Load and validate source roots, returning ``None`` when the file is absent."""

    path = source_roots_path(data_dir)
    if path.is_symlink():
        raise SourceRootConfigurationError("source-root configuration must be a regular file")
    if not path.exists():
        return None
    if not path.is_file():
        raise SourceRootConfigurationError("source-root configuration must be a regular file")
    if not _owned_by_current_user(path):
        raise SourceRootConfigurationError("source-root configuration is not owned by this user")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceRootConfigurationError("source-root configuration could not be read") from exc
    return _decode_document(payload)


def save_source_roots(data_dir: Path | str, roots: Mapping[str, Sequence[str]]) -> SourceRoots:
    """Atomically save validated source roots with private runtime permissions."""

    normalized = normalize_source_roots(roots)
    path = source_roots_path(data_dir)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.parent.chmod(0o700)
    except OSError as exc:
        raise SourceRootConfigurationError(
            "source-root configuration directory could not be secured"
        ) from exc
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SourceRootConfigurationError("source-root configuration must be a regular file")
    if path.exists() and not _owned_by_current_user(path):
        raise SourceRootConfigurationError("source-root configuration is not owned by this user")

    payload = {"version": SOURCE_ROOTS_VERSION, "roots": normalized}
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    except OSError as exc:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        raise SourceRootConfigurationError("source-root configuration could not be saved") from exc
    return normalized


def _decode_document(payload: Any) -> SourceRoots:
    if not isinstance(payload, dict):
        raise SourceRootConfigurationError("source-root configuration must be an object")
    if set(payload) != {"version", "roots"}:
        raise SourceRootConfigurationError("source-root configuration must contain only version and roots")
    version = payload["version"]
    if isinstance(version, bool) or version != SOURCE_ROOTS_VERSION:
        raise SourceRootConfigurationError(f"unsupported source-root configuration version: {version!r}")
    roots = payload["roots"]
    if not isinstance(roots, dict):
        raise SourceRootConfigurationError("source-root configuration roots must be an object")
    return normalize_source_roots(roots)


def _validate_provider_keys(roots: Mapping[str, Any]) -> None:
    for provider in roots:
        if not isinstance(provider, str) or provider not in SUPPORTED_PROVIDER_SET:
            raise SourceRootConfigurationError(f"unsupported source-root provider: {provider!r}")


def _owned_by_current_user(path: Path) -> bool:
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        return True
    try:
        return path.stat().st_uid == getuid()
    except OSError as exc:
        raise SourceRootConfigurationError("source-root configuration could not be inspected") from exc
