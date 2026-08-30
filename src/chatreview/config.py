from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID


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

    def ensure_output_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.derived_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


def default_settings(
    *,
    data_dir: Path | None = None,
    codex_root: Path | None = None,
    claude_root: Path | None = None,
    gemini_root: Path | None = None,
    git_root: Path | None = None,
) -> Settings:
    user_home = Path.home()
    configured_data = os.environ.get("CHATREVIEW_DATA_DIR")
    target_data = data_dir or (Path(configured_data) if configured_data else Path.cwd() / ".chatreview")
    configured_codex = os.environ.get("CHATREVIEW_CODEX_ROOT")
    configured_claude = os.environ.get("CHATREVIEW_CLAUDE_ROOT")
    configured_gemini = os.environ.get("CHATREVIEW_GEMINI_ROOT")
    configured_git = os.environ.get("CHATREVIEW_GIT_ROOT")
    resolved_codex = codex_root or Path(configured_codex or user_home / ".codex")
    resolved_claude = claude_root or Path(configured_claude or user_home / ".claude")
    resolved_gemini = gemini_root or Path(configured_gemini or user_home / ".gemini")
    resolved_git = git_root or Path(configured_git or user_home / "Projects")
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
        data_dir=target_data.expanduser().resolve(),
        codex_root=resolved_codex.expanduser().resolve(),
        codex_history=(resolved_codex / "history.jsonl").expanduser().resolve(),
        claude_root=resolved_claude.expanduser().resolve(),
        claude_history=(resolved_claude / "history.jsonl").expanduser().resolve(),
        gemini_root=resolved_gemini.expanduser().resolve(),
        git_root=resolved_git.expanduser().resolve(),
        raw_reasoning_retention=raw_reasoning_retention,
    )
