from __future__ import annotations

import json
import os
import platform
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

from chatreview.source_roots import (
    SUPPORTED_PROVIDERS,
    SourceRootConfigurationError,
    load_source_roots,
    normalize_source_roots,
)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = field(repr=False)
    machine_id: UUID
    machine_name: str
    contributor: str | None
    data_dir: Path
    codex_root: Path
    codex_history: Path
    claude_root: Path
    claude_history: Path
    gemini_root: Path
    git_root: Path
    codex_roots: tuple[Path, ...] | None = None
    claude_roots: tuple[Path, ...] | None = None
    gemini_roots: tuple[Path, ...] | None = None
    git_roots: tuple[Path, ...] | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    raw_reasoning_retention: Literal["preserve", "redact"] = "preserve"

    @property
    def derived_dir(self) -> Path:
        return self.data_dir / "derived"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def git_sources_dir(self) -> Path:
        return self.data_dir / "git-sources"

    def roots_for(self, provider: str, *, refresh_runtime: bool = False) -> tuple[Path, ...]:
        """Return every configured root for ``provider`` on this machine.

        Manually constructed legacy ``Settings`` values have no plural tuple,
        so they continue to expose their singular root.  The setup UI may ask
        for a fresh runtime read after saving ``source-roots.json`` without
        requiring the long-running web process to restart.
        """

        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported source provider: {provider}")
        if refresh_runtime:
            try:
                runtime = load_source_roots(self.data_dir)
            except SourceRootConfigurationError as exc:
                raise ValueError(str(exc)) from exc
            if runtime is not None:
                return tuple(Path(path) for path in runtime[provider])
        plural = getattr(self, f"{provider}_roots")
        if plural is not None:
            return plural
        return (getattr(self, f"{provider}_root"),)

    def ensure_output_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


def default_settings(
    *,
    data_dir: Path | None = None,
    codex_root: Path | Sequence[Path] | None = None,
    claude_root: Path | Sequence[Path] | None = None,
    gemini_root: Path | Sequence[Path] | None = None,
    git_root: Path | Sequence[Path] | None = None,
) -> Settings:
    user_home = Path.home()
    configured_data = os.environ.get("CHATREVIEW_DATA_DIR")
    target_data = data_dir or (Path(configured_data) if configured_data else Path.cwd() / ".chatreview")
    resolved_data = target_data.expanduser().resolve()
    try:
        runtime_roots = load_source_roots(resolved_data)
    except SourceRootConfigurationError as exc:
        raise ValueError(str(exc)) from exc
    explicit = {
        "codex": codex_root,
        "claude": claude_root,
        "gemini": gemini_root,
        "git": git_root,
    }
    defaults = {
        "codex": user_home / ".codex",
        "claude": user_home / ".claude",
        "gemini": user_home / ".gemini",
        "git": user_home / "Projects",
    }
    resolved_roots: dict[str, tuple[Path, ...]] = {}
    for provider in SUPPORTED_PROVIDERS:
        selected = _configured_roots(
            provider,
            explicit=explicit[provider],
            runtime=runtime_roots,
            fallback=defaults[provider],
        )
        resolved_roots[provider] = tuple(Path(path) for path in selected)

    # Singular fields remain compatibility aliases.  When a provider is
    # explicitly disabled, the alias is never consulted by multi-root-aware
    # code but stays a valid Path for older integrations.
    resolved_codex = _first_or_default(resolved_roots["codex"], defaults["codex"])
    resolved_claude = _first_or_default(resolved_roots["claude"], defaults["claude"])
    resolved_gemini = _first_or_default(resolved_roots["gemini"], defaults["gemini"])
    resolved_git = _first_or_default(resolved_roots["git"], defaults["git"])
    database_url = os.environ.get("CHATREVIEW_DATABASE_URL", "").strip()
    machine_id_text = os.environ.get("CHATREVIEW_MACHINE_ID", "").strip()
    if not database_url:
        raise ValueError("CHATREVIEW_DATABASE_URL is required (for example postgresql:///chatreview?port=6543)")
    if not machine_id_text:
        raise ValueError("CHATREVIEW_MACHINE_ID is required and must be a configured UUID")
    try:
        machine_id = UUID(machine_id_text)
    except ValueError as exc:
        raise ValueError("CHATREVIEW_MACHINE_ID must be a UUID") from exc
    raw_reasoning_retention = os.environ.get(
        "CHATREVIEW_RAW_REASONING_RETENTION", "preserve"
    ).strip().lower()
    if raw_reasoning_retention not in {"preserve", "redact"}:
        raise ValueError(
            "CHATREVIEW_RAW_REASONING_RETENTION must be 'preserve' or 'redact'"
        )
    return Settings(
        database_url=database_url,
        machine_id=machine_id,
        machine_name=os.environ.get("CHATREVIEW_MACHINE_NAME", platform.node()).strip() or platform.node(),
        contributor=os.environ.get("CHATREVIEW_CONTRIBUTOR") or None,
        data_dir=resolved_data,
        codex_root=resolved_codex,
        codex_history=(resolved_codex / "history.jsonl").resolve(strict=False),
        claude_root=resolved_claude,
        claude_history=(resolved_claude / "history.jsonl").resolve(strict=False),
        gemini_root=resolved_gemini,
        git_root=resolved_git,
        codex_roots=resolved_roots["codex"],
        claude_roots=resolved_roots["claude"],
        gemini_roots=resolved_roots["gemini"],
        git_roots=resolved_roots["git"],
        raw_reasoning_retention=raw_reasoning_retention,
    )


def _configured_roots(
    provider: str,
    *,
    explicit: Path | Sequence[Path] | None,
    runtime: dict[str, list[str]] | None,
    fallback: Path,
) -> list[str]:
    if explicit is not None:
        values = [explicit] if isinstance(explicit, Path) else list(explicit)
        return normalize_source_roots({provider: [str(path) for path in values]})[provider]
    if runtime is not None:
        return runtime[provider]

    plural_key = f"CHATREVIEW_{provider.upper()}_ROOTS"
    if plural_key in os.environ:
        raw = os.environ[plural_key]
        try:
            values = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{plural_key} must be a JSON array of paths") from exc
        try:
            return normalize_source_roots({provider: values})[provider]
        except SourceRootConfigurationError as exc:
            raise ValueError(f"{plural_key}: {exc}") from exc

    singular = os.environ.get(f"CHATREVIEW_{provider.upper()}_ROOT")
    value = singular if singular is not None else str(fallback)
    try:
        return normalize_source_roots({provider: [value]})[provider]
    except SourceRootConfigurationError as exc:
        raise ValueError(str(exc)) from exc


def _first_or_default(roots: tuple[Path, ...], fallback: Path) -> Path:
    return roots[0] if roots else fallback.expanduser().resolve(strict=False)
