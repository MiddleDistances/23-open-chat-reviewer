from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from chatreview.providers.base import (
    ProviderAdapter,
    add_fragment,
    extract_common_artifacts,
    json_text,
    source_kind,
)
from chatreview.types import Artifact, ParsedRecord, SourceSpec, TextFragment


class ClaudeAdapter(ProviderAdapter):
    name = "claude"
    parser_version = 3

    def __init__(self, root: Path) -> None:
        self.root = root

    def discover(self) -> list[SourceSpec]:
        found: list[SourceSpec] = []
        projects = self.root / "projects"
        if projects.exists():
            for directory, names, files in os.walk(projects, followlinks=False):
                names.sort()
                for filename in sorted(files):
                    if filename.endswith(".jsonl"):
                        path = Path(directory) / filename
                        found.append(SourceSpec(self.name, path, source_kind(path, provider=self.name)))
        history = self.root / "history.jsonl"
        if history.is_file():
            found.append(SourceSpec(self.name, history, "history"))
        return sorted(found, key=lambda item: str(item.path))

    def parse(self, data: dict[str, Any], source: SourceSpec) -> ParsedRecord:
        if source.source_kind == "history":
            return self._parse_history(data)

        event_type = _string(data.get("type")) or "unknown"
        message = data.get("message")
        role = _string(message.get("role")) if isinstance(message, dict) else None
        subtype = _string(data.get("subtype"))
        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []

        if isinstance(message, dict):
            self._extract_message(message, fragments, artifacts)
        elif isinstance(message, str):
            add_fragment(
                fragments,
                artifacts,
                kind=f"{event_type}-message",
                value=message,
                is_error=bool(data.get("isApiErrorMessage")),
            )

        if event_type == "system":
            add_fragment(
                fragments,
                artifacts,
                kind="system-message",
                value=data.get("content"),
                label=subtype,
                is_error=subtype in {"error", "api_error"},
            )
        elif event_type == "attachment":
            _extract_attachment(data.get("attachment"), fragments, artifacts)
        elif event_type in {"queue-operation", "last-prompt", "ai-title"}:
            value = data.get("content") or data.get("lastPrompt") or data.get("aiTitle")
            add_fragment(fragments, artifacts, kind=event_type, value=value)

        metadata = _selected_metadata(data)
        cwd = _string(data.get("cwd"))
        project = cwd or _project_from_path(source.path)
        parent_session_id = _string(data.get("sessionId")) or _parent_session_from_path(source.path)
        subagent_id = _subagent_from_path(source.path)
        session_id = (
            f"{parent_session_id}:subagent:{subagent_id}"
            if subagent_id and parent_session_id
            else parent_session_id or _session_from_path(source.path)
        )
        artifacts = extract_common_artifacts(fragments, artifacts)
        return ParsedRecord(
            provider=self.name,
            session_external_id=session_id,
            event_type=event_type,
            parent_session_external_id=parent_session_id if subagent_id else None,
            subtype=subtype,
            role=role or (event_type if event_type in {"user", "assistant", "system"} else None),
            timestamp=_string(data.get("timestamp")),
            provider_event_id=_string(data.get("uuid")) or _string(data.get("key")),
            parent_event_id=_string(data.get("parentUuid")),
            turn_id=_string(data.get("promptId")) or _string(data.get("requestId")),
            cwd=cwd,
            project=project,
            metadata=metadata,
            fragments=fragments,
            artifacts=artifacts,
        )

    def normalize_project(self, value: str | None) -> str | None:
        return _decode_project_directory(value) if value else None

    def _parse_history(self, data: dict[str, Any]) -> ParsedRecord:
        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []
        add_fragment(fragments, artifacts, kind="user-message", value=data.get("display"))
        pasted = data.get("pastedContents")
        if pasted:
            add_fragment(fragments, artifacts, kind="pasted-content", value=pasted)
        timestamp = data.get("timestamp")
        project = self.normalize_project(_string(data.get("project")))
        return ParsedRecord(
            provider=self.name,
            session_external_id=_string(data.get("sessionId")),
            event_type="history",
            subtype="user-prompt",
            role="user",
            timestamp=str(timestamp) if timestamp is not None else None,
            cwd=project,
            project=project,
            fragments=fragments,
            artifacts=extract_common_artifacts(fragments, artifacts),
        )

    def _extract_message(
        self,
        message: dict[str, Any],
        fragments: list[TextFragment],
        artifacts: list[Artifact],
    ) -> None:
        role = _string(message.get("role")) or "message"
        content = message.get("content")
        if isinstance(content, str):
            add_fragment(fragments, artifacts, kind=f"{role}-message", value=content)
            return
        for block in content if isinstance(content, list) else []:
            if isinstance(block, str):
                add_fragment(fragments, artifacts, kind=f"{role}-message", value=block)
                continue
            if not isinstance(block, dict):
                continue
            block_type = _string(block.get("type")) or "unknown"
            if block_type == "text":
                add_fragment(fragments, artifacts, kind=f"{role}-message", value=block.get("text"))
            elif block_type == "thinking":
                add_fragment(fragments, artifacts, kind="reasoning", value=block.get("thinking"))
            elif block_type == "tool_use":
                tool_name = _string(block.get("name")) or "tool"
                tool_input = block.get("input")
                add_fragment(fragments, artifacts, kind="tool-input", value=tool_input, label=tool_name)
                artifacts.append(Artifact("tool", tool_name))
                _extract_command(tool_name, tool_input, artifacts)
            elif block_type == "tool_result":
                _extract_tool_result(block, fragments, artifacts)
            elif block_type in {"image", "document"}:
                descriptor = _media_descriptor(block)
                add_fragment(fragments, artifacts, kind="media", value=descriptor, label=block_type)
                artifacts.append(Artifact("attachment", descriptor, block_type))
            else:
                for key in ("text", "content", "message"):
                    if key in block:
                        add_fragment(
                            fragments,
                            artifacts,
                            kind=f"block-{block_type}",
                            value=block[key],
                            label=block_type,
                        )


def _extract_tool_result(
    block: dict[str, Any], fragments: list[TextFragment], artifacts: list[Artifact]
) -> None:
    content = block.get("content")
    is_error = bool(block.get("is_error"))
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                add_fragment(
                    fragments,
                    artifacts,
                    kind="tool-output",
                    value=item.get("text") or item.get("content") or _media_descriptor(item),
                    label=_string(block.get("tool_use_id")),
                    is_error=is_error,
                )
            else:
                add_fragment(
                    fragments,
                    artifacts,
                    kind="tool-output",
                    value=item,
                    label=_string(block.get("tool_use_id")),
                    is_error=is_error,
                )
    else:
        add_fragment(
            fragments,
            artifacts,
            kind="tool-output",
            value=content,
            label=_string(block.get("tool_use_id")),
            is_error=is_error,
        )


def _extract_command(tool_name: str, tool_input: Any, artifacts: list[Artifact]) -> None:
    if not isinstance(tool_input, dict):
        return
    for key in ("cmd", "command", "chars"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            artifacts.append(Artifact("command", value.strip(), tool_name))


def _extract_attachment(attachment: Any, fragments: list[TextFragment], artifacts: list[Artifact]) -> None:
    if not isinstance(attachment, dict):
        return
    name = _string(attachment.get("fileName")) or _string(attachment.get("name")) or "attachment"
    artifacts.append(Artifact("attachment", name))
    for key in ("extractedContent", "text", "content"):
        value = attachment.get(key)
        if isinstance(value, (str, list, dict)):
            add_fragment(fragments, artifacts, kind="attachment-text", value=value, label=name)


def _media_descriptor(block: dict[str, Any]) -> str:
    source = block.get("source")
    if isinstance(source, dict):
        media_type = source.get("media_type") or source.get("type") or "binary"
        data = source.get("data")
        size = len(data) if isinstance(data, str) else None
        return f"[{media_type} attachment{f', {size} encoded characters' if size else ''}]"
    return f"[{block.get('type', 'media')} attachment]"


def _selected_metadata(data: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "entrypoint",
        "gitBranch",
        "isSidechain",
        "isMeta",
        "userType",
        "version",
        "slug",
        "requestId",
        "promptId",
        "sourceToolAssistantUUID",
        "permissionMode",
        "agentId",
        "attributionMcpServer",
        "attributionMcpTool",
        "durationMs",
        "messageCount",
        "operation",
    )
    metadata = {key: data[key] for key in keys if key in data and _small(data[key])}
    if data.get("toolUseResult") is not None and _small(data["toolUseResult"]):
        metadata["toolUseResult"] = data["toolUseResult"]
    return metadata


def _small(value: Any) -> bool:
    return len(json_text(value)) <= 8192


def _project_from_path(path: Path) -> str | None:
    try:
        projects_index = path.parts.index("projects")
        return _decode_project_directory(path.parts[projects_index + 1])
    except (ValueError, IndexError):
        return None


@lru_cache(maxsize=256)
def _decode_project_directory(encoded: str) -> str:
    """Resolve Claude's slash-to-dash project key against existing local directories."""
    home = Path.home()
    candidate_roots = [home]
    documents = home / "Documents"
    if documents.is_dir():
        candidate_roots.append(documents)
    for root in candidate_roots:
        try:
            candidates = [root, *(item for item in root.iterdir() if item.is_dir())]
        except OSError:
            continue
        for candidate in candidates:
            if candidate.as_posix().replace("/", "-") == encoded:
                return str(candidate)
    return encoded


def _session_from_path(path: Path) -> str:
    if path.name == "journal.jsonl":
        return f"journal:{path.parent.name}"
    return path.stem


def _subagent_from_path(path: Path) -> str | None:
    return path.stem if "subagents" in path.parts else None


def _parent_session_from_path(path: Path) -> str | None:
    try:
        return path.parts[path.parts.index("subagents") - 1]
    except (ValueError, IndexError):
        return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
