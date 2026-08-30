from __future__ import annotations

import os
import re
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

SESSION_ID_PATTERN = re.compile(r"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})", re.I)


class CodexAdapter(ProviderAdapter):
    name = "codex"
    parser_version = 3

    def __init__(self, root: Path) -> None:
        self.root = root

    def discover(self) -> list[SourceSpec]:
        found: list[SourceSpec] = []
        sessions = self.root / "sessions"
        if sessions.exists():
            for directory, names, files in os.walk(sessions, followlinks=False):
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
            return self._parse_history(data, source)

        outer_type = str(data.get("type") or "unknown")
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        subtype = _string(payload.get("type"))
        if outer_type == "session_meta":
            session_id = _session_from_payload(payload) or _session_from_path(source.path)
        else:
            session_id = _string(payload.get("session_id")) or _session_from_path(source.path)
        timestamp = _string(data.get("timestamp")) or _string(payload.get("timestamp"))
        role = _string(payload.get("role"))
        passthrough = payload.get("internal_chat_message_metadata_passthrough")
        turn_id = _string(payload.get("turn_id"))
        if not turn_id and isinstance(passthrough, dict):
            turn_id = _string(passthrough.get("turn_id"))

        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []
        provider_event_id = _string(payload.get("id")) or _string(payload.get("call_id"))
        parent_event_id = _string(payload.get("parent_id"))

        if outer_type == "response_item":
            self._extract_response_item(payload, fragments, artifacts)
        elif outer_type == "event_msg":
            message_kind = "error" if subtype in {"error", "warning", "stream_error"} else "event-message"
            add_fragment(
                fragments,
                artifacts,
                kind=message_kind,
                value=payload.get("message"),
                label=subtype,
                is_error=message_kind == "error",
            )
        elif outer_type == "compacted":
            add_fragment(fragments, artifacts, kind="compaction-summary", value=payload.get("message"))
            _extract_history(payload.get("replacement_history"), fragments, artifacts)
        elif outer_type == "turn_context":
            add_fragment(fragments, artifacts, kind="context-summary", value=payload.get("summary"))
        elif outer_type in {"inter_agent_communication_metadata", "ghost_snapshot"}:
            add_fragment(fragments, artifacts, kind="agent-metadata", value=payload.get("message"))

        metadata = _selected_metadata(payload)
        cwd = _string(payload.get("cwd"))
        project = cwd
        if outer_type == "session_meta":
            session_id = _session_from_payload(payload) or session_id
            model = payload.get("model_provider")
            if model:
                metadata["model_provider"] = model
            git = payload.get("git")
            if isinstance(git, dict):
                metadata["git"] = {
                    key: git.get(key) for key in ("branch", "commit_hash", "repository_url") if git.get(key)
                }

        artifacts = extract_common_artifacts(fragments, artifacts)
        return ParsedRecord(
            provider=self.name,
            session_external_id=session_id,
            event_type=outer_type,
            parent_session_external_id=_parent_session_from_payload(payload),
            subtype=subtype,
            role=role,
            timestamp=timestamp,
            provider_event_id=provider_event_id,
            parent_event_id=parent_event_id,
            turn_id=turn_id,
            cwd=cwd,
            project=project,
            metadata=metadata,
            fragments=fragments,
            artifacts=artifacts,
        )

    def _parse_history(self, data: dict[str, Any], source: SourceSpec) -> ParsedRecord:
        del source
        fragments: list[TextFragment] = []
        artifacts: list[Artifact] = []
        add_fragment(fragments, artifacts, kind="user-message", value=data.get("text"))
        timestamp = data.get("ts")
        return ParsedRecord(
            provider=self.name,
            session_external_id=_string(data.get("session_id")),
            event_type="history",
            subtype="user-prompt",
            role="user",
            timestamp=str(timestamp) if timestamp is not None else None,
            fragments=fragments,
            artifacts=extract_common_artifacts(fragments, artifacts),
        )

    def _extract_response_item(
        self,
        payload: dict[str, Any],
        fragments: list[TextFragment],
        artifacts: list[Artifact],
    ) -> None:
        item_type = _string(payload.get("type")) or "response-item"
        if item_type == "message":
            for item in _as_list(payload.get("content")):
                if isinstance(item, dict):
                    block_type = _string(item.get("type")) or "text"
                    value = item.get("text") or item.get("content")
                    add_fragment(
                        fragments,
                        artifacts,
                        kind=_message_kind(_string(payload.get("role")), block_type),
                        value=value,
                        label=block_type,
                    )
                elif isinstance(item, str):
                    add_fragment(fragments, artifacts, kind="message", value=item)
        elif item_type in {"function_call", "custom_tool_call"}:
            tool_name = _string(payload.get("name")) or item_type
            arguments = payload.get("arguments", payload.get("input"))
            add_fragment(fragments, artifacts, kind="tool-input", value=arguments, label=tool_name)
            artifacts.append(Artifact("tool", tool_name))
            _extract_command(tool_name, arguments, artifacts)
        elif item_type in {"function_call_output", "custom_tool_call_output"}:
            output = payload.get("output", payload.get("content"))
            add_fragment(
                fragments,
                artifacts,
                kind="tool-output",
                value=output,
                label=_string(payload.get("call_id")),
            )
        elif item_type == "reasoning":
            _extract_reasoning(payload, fragments, artifacts)
        elif item_type == "agent_message":
            add_fragment(fragments, artifacts, kind="agent-message", value=payload.get("message"))


def _extract_reasoning(
    payload: dict[str, Any], fragments: list[TextFragment], artifacts: list[Artifact]
) -> None:
    summary = payload.get("summary")
    for item in _as_list(summary):
        if isinstance(item, dict):
            add_fragment(
                fragments,
                artifacts,
                kind="reasoning",
                value=item.get("text") or item.get("summary"),
            )
        else:
            add_fragment(fragments, artifacts, kind="reasoning", value=item)
    content = payload.get("content")
    for item in _as_list(content):
        if isinstance(item, dict):
            add_fragment(fragments, artifacts, kind="reasoning", value=item.get("text"))


def _extract_history(value: Any, fragments: list[TextFragment], artifacts: list[Artifact]) -> None:
    for entry in _as_list(value):
        if not isinstance(entry, dict):
            continue
        entry_type = _string(entry.get("type")) or "compacted-history"
        if entry_type == "message":
            role = _string(entry.get("role"))
            for block in _as_list(entry.get("content")):
                if isinstance(block, dict):
                    add_fragment(
                        fragments,
                        artifacts,
                        kind=f"compacted-{role or 'message'}",
                        value=block.get("text") or block.get("content"),
                    )
                elif isinstance(block, str):
                    add_fragment(fragments, artifacts, kind=f"compacted-{role or 'message'}", value=block)
        elif entry_type in {"function_call", "custom_tool_call"}:
            add_fragment(
                fragments,
                artifacts,
                kind="compacted-tool-input",
                value=entry.get("arguments", entry.get("input")),
                label=_string(entry.get("name")),
            )
        elif entry_type in {"function_call_output", "custom_tool_call_output"}:
            add_fragment(
                fragments,
                artifacts,
                kind="compacted-tool-output",
                value=entry.get("output", entry.get("content")),
            )


def _extract_command(tool_name: str, arguments: Any, artifacts: list[Artifact]) -> None:
    parsed = arguments
    if isinstance(arguments, str):
        try:
            import orjson

            parsed = orjson.loads(arguments)
        except (ValueError, TypeError):
            parsed = None
    if not isinstance(parsed, dict):
        return
    for key in ("cmd", "command", "chars"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            artifacts.append(Artifact("command", value.strip(), tool_name))


def _selected_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "phase",
        "model",
        "originator",
        "cli_version",
        "source",
        "thread_source",
        "call_id",
        "name",
        "status",
        "started_at",
        "completed_at",
        "collaboration_mode_kind",
        "agent_id",
        "agent_path",
        "forked_from_id",
        "parent_thread_id",
    )
    return {key: payload[key] for key in keys if key in payload and _small(payload[key])}


def _small(value: Any) -> bool:
    return len(json_text(value)) <= 8192


def _session_from_payload(payload: dict[str, Any]) -> str | None:
    return _string(payload.get("session_id")) or _string(payload.get("id")) if payload else None


def _parent_session_from_payload(payload: dict[str, Any]) -> str | None:
    direct = _string(payload.get("parent_thread_id")) or _string(payload.get("forked_from_id"))
    if direct:
        return direct
    source = payload.get("source")
    if not isinstance(source, dict):
        return None
    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return None
    spawn = subagent.get("thread_spawn")
    return _string(spawn.get("parent_thread_id")) if isinstance(spawn, dict) else None


def _session_from_path(path: Path) -> str:
    match = SESSION_ID_PATTERN.search(path.name)
    return match.group(1) if match else f"file:{path.name}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _message_kind(role: str | None, block_type: str) -> str:
    if role in {"user", "assistant", "developer", "system"}:
        return f"{role}-message"
    return "reasoning" if "reason" in block_type else "message"
