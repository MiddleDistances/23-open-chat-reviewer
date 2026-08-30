from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceSpec:
    provider: str
    path: Path
    source_kind: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TextFragment:
    kind: str
    text: str
    label: str | None = None
    is_error: bool = False


@dataclass(slots=True)
class Artifact:
    kind: str
    value: str
    label: str | None = None


@dataclass(slots=True)
class ParsedRecord:
    provider: str
    session_external_id: str | None
    event_type: str
    parent_session_external_id: str | None = None
    subtype: str | None = None
    role: str | None = None
    timestamp: str | None = None
    provider_event_id: str | None = None
    parent_event_id: str | None = None
    turn_id: str | None = None
    cwd: str | None = None
    project: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    fragments: list[TextFragment] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
