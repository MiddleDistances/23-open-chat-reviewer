from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import orjson

from chatreview.providers.base import (
    ProviderAdapter,
    add_fragment,
    extract_common_artifacts,
    json_text,
    stable_hash,
)
from chatreview.types import Artifact, ParsedRecord, SourceSpec, TextFragment


class GeminiAdapter(ProviderAdapter):
    """Read Gemini CLI JSON documents without treating them as Claude JSONL."""

    name = "gemini"
    parser_version = 1

    def __init__(self, root: Path) -> None:
        self.root = root
        self._project_paths = self._load_project_paths()

    def discover(self) -> list[SourceSpec]:
        found: list[SourceSpec] = []
        temporary_projects = self.root / "tmp"
        if not temporary_projects.is_dir():
            return found
        for directory_name in sorted(os.listdir(temporary_projects)):
            directory = temporary_projects / directory_name
            if not directory.is_dir() or directory.is_symlink():
                continue
            chats = directory / "chats"
            provenance = self._project_provenance(directory)
            if chats.is_dir():
                for path in sorted(chats.glob("session-*.json")):
                    if path.is_file() and not path.is_symlink():
                        found.append(SourceSpec(self.name, path, "session", provenance))
            history = directory / "logs.json"
            if history.is_file() and not history.is_symlink():
                found.append(SourceSpec(self.name, history, "history", provenance))
        return sorted(found, key=lambda item: str(item.path))

    def record_format(self, source: SourceSpec) -> Literal["json-document"]:
        del source
        return "json-document"

    def parse(self, data: dict[str, Any], source: SourceSpec) -> ParsedRecord:
        records = self.parse_many(data, source)
        if len(records) != 1:
            raise ValueError("Gemini JSON documents project to multiple records; use parse_many")
        return records[0]

    def parse_many(self, data: Any, source: SourceSpec) -> list[ParsedRecord]:
        if source.source_kind == "history":
            return self._parse_history_document(data, source)
        return self._parse_session_document(data, source)

    def normalize_project(self, value: str | None) -> str | None:
        return value

    def _parse_session_document(self, data: Any, source: SourceSpec) -> list[ParsedRecord]:
        if not isinstance(data, dict):
            raise ValueError("Gemini session document is not an object")
        session_id = _string(data.get("sessionId"))
        if not session_id:
            raise ValueError("Gemini session document has no sessionId")
        project_hash = _string(data.get("projectHash"))
        cwd, project = self._resolve_project(source, project_hash)
        records = [
            self._session_metadata_record(
                data,
                session_id=session_id,
                project_hash=project_hash,
                cwd=cwd,
                project=project,
            )
        ]
        messages = data.get("messages")
        if not isinstance(messages, list):
            raise ValueError("Gemini session document has no messages array")
        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("Gemini session message is not an object")
            records.append(
                self._message_record(
                    message,
                    session_id=session_id,
                    project_hash=project_hash,
                    cwd=cwd,
                    project=project,
                )
            )
        return records

    def _session_metadata_record(
        self,
        data: dict[str, Any],
        *,
        session_id: str,
        project_hash: str | None,
        cwd: str | None,
        project: str | None,
    ) -> ParsedRecord:
        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []
        add_fragment(
            fragments,
            artifacts,
            kind="session-summary",
            value=data.get("summary"),
        )
        metadata = _compact_metadata(
            {
                "project_hash": project_hash,
                "last_updated": data.get("lastUpdated"),
                "kind": data.get("kind"),
            }
        )
        return ParsedRecord(
            provider=self.name,
            session_external_id=session_id,
            event_type="session_meta",
            timestamp=_string(data.get("startTime")),
            cwd=cwd,
            project=project,
            metadata=metadata,
            fragments=fragments,
            artifacts=extract_common_artifacts(fragments, artifacts),
        )

    def _message_record(
        self,
        message: dict[str, Any],
        *,
        session_id: str,
        project_hash: str | None,
        cwd: str | None,
        project: str | None,
    ) -> ParsedRecord:
        raw_type = _string(message.get("type")) or "unknown"
        role = (
            "user"
            if raw_type == "user"
            else "assistant"
            if raw_type == "gemini"
            else "system"
            if raw_type == "system"
            else None
        )
        event_type = "message" if role else raw_type
        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []
        content_kind = f"{role}-message" if role else f"{raw_type}-message"
        _add_content(
            fragments,
            artifacts,
            kind=content_kind,
            value=message.get("content"),
            is_error=raw_type == "error",
        )
        _add_content(
            fragments,
            artifacts,
            kind="display-content",
            value=message.get("displayContent"),
            is_error=raw_type == "error",
        )
        for thought in _dict_items(message.get("thoughts")):
            # Gemini CLI labels these persisted fields as thought descriptions.
            # Preserve only that explicit summary; no hidden reasoning is inferred.
            add_fragment(
                fragments,
                artifacts,
                kind="reasoning-summary",
                value=thought.get("description"),
                label=_string(thought.get("subject")),
            )
        tool_statuses: list[dict[str, str]] = []
        for tool_call in _dict_items(message.get("toolCalls")):
            tool_name = _string(tool_call.get("name")) or _string(tool_call.get("displayName"))
            label = tool_name or "tool"
            add_fragment(
                fragments,
                artifacts,
                kind="tool-input",
                value=_safe_evidence(tool_call.get("args")),
                label=label,
            )
            status = _string(tool_call.get("status"))
            add_fragment(
                fragments,
                artifacts,
                kind="tool-output",
                value=_safe_evidence(tool_call.get("result")),
                label=label,
                is_error=status == "error",
            )
            add_fragment(
                fragments,
                artifacts,
                kind="tool-output-display",
                value=_safe_evidence(tool_call.get("resultDisplay")),
                label=label,
                is_error=status == "error",
            )
            if tool_name:
                artifacts.append(Artifact("tool", tool_name))
            if tool_call.get("args") is not None:
                artifacts.append(Artifact("tool-input", json_text(_safe_evidence(tool_call["args"])), label))
            if status:
                tool_statuses.append({"name": label, "status": status})
        metadata = _compact_metadata(
            {
                "project_hash": project_hash,
                "model": message.get("model"),
                "tokens": message.get("tokens"),
                "tool_statuses": tool_statuses,
            }
        )
        return ParsedRecord(
            provider=self.name,
            session_external_id=session_id,
            event_type=event_type,
            subtype=raw_type,
            role=role,
            timestamp=_string(message.get("timestamp")),
            provider_event_id=_string(message.get("id")),
            cwd=cwd,
            project=project,
            metadata=metadata,
            fragments=fragments,
            artifacts=extract_common_artifacts(fragments, artifacts),
        )

    def _parse_history_document(self, data: Any, source: SourceSpec) -> list[ParsedRecord]:
        if not isinstance(data, list):
            raise ValueError("Gemini history document is not an array")
        cwd, project = self._resolve_project(source, None)
        records: list[ParsedRecord] = []
        for entry in data:
            if not isinstance(entry, dict):
                raise ValueError("Gemini history entry is not an object")
            fragments: list[TextFragment] = []
            artifacts: list[Artifact] = []
            add_fragment(
                fragments,
                artifacts,
                kind="user-message",
                value=entry.get("message"),
            )
            raw_type = _string(entry.get("type"))
            records.append(
                ParsedRecord(
                    provider=self.name,
                    session_external_id=_string(entry.get("sessionId")),
                    event_type="history",
                    subtype=raw_type,
                    role="user" if raw_type == "user" else None,
                    timestamp=_string(entry.get("timestamp")),
                    provider_event_id=(
                        f"history:{entry['sessionId']}:{entry['messageId']}"
                        if entry.get("sessionId") is not None and entry.get("messageId") is not None
                        else None
                    ),
                    cwd=cwd,
                    project=project,
                    fragments=fragments,
                    artifacts=extract_common_artifacts(fragments, artifacts),
                )
            )
        if records:
            return records
        return [
            ParsedRecord(
                provider=self.name,
                session_external_id=None,
                event_type="history-container",
                cwd=cwd,
                project=project,
                metadata={"record_count": 0},
            )
        ]

    def _load_project_paths(self) -> dict[str, tuple[str, str]]:
        projects_file = self.root / "projects.json"
        if not projects_file.is_file():
            return {}
        try:
            payload = projects_file.read_bytes()
            data = orjson.loads(payload)
        except (OSError, orjson.JSONDecodeError):
            return {}
        projects = data.get("projects") if isinstance(data, dict) else None
        if not isinstance(projects, dict):
            return {}
        payload_hash = stable_hash(payload)
        return {
            storage_name: (project_path, payload_hash)
            for project_path, storage_name in projects.items()
            if isinstance(project_path, str) and isinstance(storage_name, str)
        }

    def _project_provenance(self, project_directory: Path) -> dict[str, Any]:
        provenance: dict[str, Any] = {"project_storage": project_directory.name}
        marker = project_directory / ".project_root"
        if marker.is_file():
            try:
                payload = marker.read_bytes()
                value = payload.decode("utf-8").strip()
            except (OSError, UnicodeDecodeError):
                value = ""
            if value:
                provenance.update(
                    {
                        "project_root": value,
                        "evidence_kind": "project-root-marker",
                        "evidence_sha256": stable_hash(payload),
                    }
                )
                return provenance
        mapped = self._project_paths.get(project_directory.name)
        if mapped:
            project_root, payload_hash = mapped
            provenance.update(
                {
                    "project_root": project_root,
                    "evidence_kind": "projects-json-mapping",
                    "evidence_sha256": payload_hash,
                }
            )
        return provenance

    def _resolve_project(
        self, source: SourceSpec, project_hash: str | None
    ) -> tuple[str | None, str | None]:
        resolved = _string(source.provenance.get("project_root"))
        if resolved:
            return resolved, resolved
        # A 64-character project hash is a real persisted identifier, but it is
        # not a filesystem path. Preserve it as project identity and leave cwd null.
        return None, project_hash


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _add_content(
    fragments: list[TextFragment],
    artifacts: list[Artifact],
    *,
    kind: str,
    value: Any,
    is_error: bool,
) -> None:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and "text" in item:
                add_fragment(
                    fragments,
                    artifacts,
                    kind=kind,
                    value=item.get("text"),
                    is_error=is_error,
                )
            elif isinstance(item, dict) and "functionResponse" in item:
                response = item.get("functionResponse")
                label = _string(response.get("name")) if isinstance(response, dict) else None
                add_fragment(
                    fragments,
                    artifacts,
                    kind="tool-output",
                    value=_safe_evidence(response),
                    label=label,
                    is_error=is_error,
                )
            elif isinstance(item, dict):
                descriptor = _attachment_descriptor(item)
                add_fragment(fragments, artifacts, kind="attachment", value=descriptor)
                artifacts.append(Artifact("attachment", descriptor))
            else:
                add_fragment(
                    fragments,
                    artifacts,
                    kind=kind,
                    value=item,
                    is_error=is_error,
                )
        return
    add_fragment(fragments, artifacts, kind=kind, value=value, is_error=is_error)


def _attachment_descriptor(value: dict[str, Any]) -> str:
    inline = value.get("inlineData")
    if isinstance(inline, dict):
        mime_type = _string(inline.get("mimeType")) or "binary"
        encoded = inline.get("data")
        size = len(encoded) if isinstance(encoded, str) else 0
        return f"[{mime_type} attachment, {size} encoded characters]"
    file_data = value.get("fileData")
    if isinstance(file_data, dict):
        mime_type = _string(file_data.get("mimeType")) or "file"
        uri = _string(file_data.get("fileUri"))
        return f"[{mime_type} attachment{f': {uri}' if uri else ''}]"
    return f"[Gemini attachment fields: {', '.join(sorted(value))}]"


def _safe_evidence(value: Any) -> Any:
    if isinstance(value, list):
        return [_safe_evidence(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "inlineData" in value or "fileData" in value:
        return _attachment_descriptor(value)
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key == "data" and isinstance(item, str) and len(item) >= 1024:
            result[key] = f"[opaque encoded payload: {len(item)} characters]"
        else:
            result[key] = _safe_evidence(item)
    return result


def _compact_metadata(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value not in (None, "", [], {}) and len(json_text(value)) <= 8192
    }


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
