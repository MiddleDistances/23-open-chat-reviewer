from __future__ import annotations

from pathlib import Path

from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.providers.base import (
    is_actionable_error_signature,
    is_reportable_error_signature,
)
from chatreview.types import SourceSpec


def test_codex_compaction_extracts_replacement_history() -> None:
    adapter = CodexAdapter(Path("/tmp/codex"))
    source = SourceSpec(
        "codex",
        Path("rollout-11111111-1111-1111-1111-111111111111.jsonl"),
        "session",
    )
    parsed = adapter.parse(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "compacted",
            "payload": {
                "message": "A compact summary",
                "replacement_history": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "text", "text": "Old objective"}],
                    },
                    {"type": "function_call", "name": "exec", "arguments": '{"cmd":"make test"}'},
                ],
            },
        },
        source,
    )
    assert parsed.session_external_id == "11111111-1111-1111-1111-111111111111"
    assert {item.kind for item in parsed.fragments} >= {
        "compaction-summary",
        "compacted-user",
        "compacted-tool-input",
    }


def test_claude_media_is_described_not_copied() -> None:
    adapter = ClaudeAdapter(Path("/tmp/claude"))
    source = SourceSpec("claude", Path("session.jsonl"), "session")
    parsed = adapter.parse(
        {
            "type": "assistant",
            "sessionId": "session",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "image",
                        "source": {"media_type": "image/png", "data": "a" * 20_000},
                    }
                ],
            },
        },
        source,
    )
    assert parsed.fragments[0].text == "[image/png attachment, 20000 encoded characters]"
    assert all("a" * 100 not in fragment.text for fragment in parsed.fragments)


def test_subagent_sessions_retain_parent_chat_identity() -> None:
    codex = CodexAdapter(Path("/tmp/codex"))
    codex_source = SourceSpec(
        "codex",
        Path("rollout-aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.jsonl"),
        "session",
    )
    codex_record = codex.parse(
        {
            "type": "session_meta",
            "payload": {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "parent_thread_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            },
        },
        codex_source,
    )
    assert codex_record.parent_session_external_id == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    claude = ClaudeAdapter(Path("/tmp/claude"))
    claude_source = SourceSpec(
        "claude",
        Path("projects/project/parent-chat/subagents/agent-child.jsonl"),
        "subagent",
    )
    claude_record = claude.parse(
        {
            "type": "user",
            "sessionId": "parent-chat",
            "message": {"role": "user", "content": "delegated work"},
        },
        claude_source,
    )
    assert claude_record.session_external_id == "parent-chat:subagent:agent-child"
    assert claude_record.parent_session_external_id == "parent-chat"


def test_actionable_error_classifier_rejects_failure_prose_and_code() -> None:
    assert is_actionable_error_signature("Traceback (most recent call last):")
    assert is_actionable_error_signature("RuntimeError: database is unavailable")
    assert is_actionable_error_signature("FAILED tests/test_widget.py::test_save")
    assert is_actionable_error_signature("write_stdin failed: stdin is closed")
    assert is_actionable_error_signature("Process exited with code 2")
    assert not is_actionable_error_signature("During execution, inspect repeated errors")
    assert not is_actionable_error_signature("except ValueError:")
    assert not is_actionable_error_signature("tests passed or failed;")
    assert not is_reportable_error_signature("Traceback (most recent call last):")
    assert not is_reportable_error_signature("error: null,")
    assert not is_reportable_error_signature("scheduleError: string | null;")
    assert not is_reportable_error_signature("The services are not failed: workers are active")
    assert is_reportable_error_signature("ModuleNotFoundError: No module named 'psycopg2'")
