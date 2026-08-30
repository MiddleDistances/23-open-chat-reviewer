from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID, uuid4

import orjson
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from chatreview.config import Settings
from chatreview.db import close_pools, migrate


def write_jsonl(path: Path, records: list[dict | bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for record in records:
            handle.write(record if isinstance(record, bytes) else orjson.dumps(record))
            handle.write(b"\n")


@pytest.fixture()
def postgres_database_url() -> str:
    schema = f"test_{uuid4().hex}"
    base_url = os.environ.get(
        "CHATREVIEW_TEST_DATABASE_URL", "postgresql:///chatreview?port=6543"
    )
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')
    parameters = conninfo_to_dict(base_url)
    existing_options = parameters.get("options", "").strip()
    parameters["options"] = f"{existing_options} -c search_path={schema},public".strip()
    database_url = make_conninfo(**parameters)
    migrate(database_url)
    try:
        yield database_url
    finally:
        close_pools()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture()
def corpus(tmp_path: Path, postgres_database_url: str) -> tuple[Settings, Path, Path]:
    codex = tmp_path / "codex"
    claude = tmp_path / "claude"
    data = tmp_path / "state"
    codex_session = (
        codex
        / "sessions"
        / "2026"
        / "07"
        / "18"
        / "rollout-2026-07-18T10-00-00-11111111-1111-1111-1111-111111111111.jsonl"
    )
    write_jsonl(
        codex_session,
        [
            {
                "timestamp": "2026-07-18T02:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "session_id": "11111111-1111-1111-1111-111111111111",
                    "cwd": "/work/codex-project",
                    "model_provider": "openai",
                },
            },
            {
                "timestamp": "2026-07-18T02:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "The frobnicator keeps failing"}],
                },
            },
            {
                "timestamp": "2026-07-18T02:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": '{"cmd":"python /work/codex-project/check.py"}',
                    "call_id": "call-1",
                },
            },
            {
                "timestamp": "2026-07-18T02:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "Fatal error: frobnicator exploded",
                },
            },
            b"{not-json}",
        ],
    )
    write_jsonl(
        codex / "history.jsonl",
        [
            {
                "session_id": "11111111-1111-1111-1111-111111111111",
                "text": "Investigate frobnicator",
                "ts": 1784340000,
            }
        ],
    )
    claude_session = (
        claude / "projects" / "-work-claude-project" / "22222222-2222-2222-2222-222222222222.jsonl"
    )
    write_jsonl(
        claude_session,
        [
            {
                "type": "user",
                "uuid": "msg-1",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "timestamp": "2026-07-18T03:00:00Z",
                "cwd": "/work/claude-project",
                "message": {"role": "user", "content": "The widget is still broken"},
            },
            {
                "type": "assistant",
                "uuid": "msg-2",
                "parentUuid": "msg-1",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "timestamp": "2026-07-18T03:00:01Z",
                "cwd": "/work/claude-project",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "Check the same assumption again"},
                        {
                            "type": "tool_use",
                            "id": "tool-1",
                            "name": "Bash",
                            "input": {"command": "pytest tests/test_widget.py"},
                        },
                    ],
                },
            },
            {
                "type": "user",
                "uuid": "msg-3",
                "parentUuid": "msg-2",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "timestamp": "2026-07-18T03:00:02Z",
                "cwd": "/work/claude-project",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "is_error": True,
                            "content": "FAILED test_widget",
                        }
                    ],
                },
            },
        ],
    )
    write_jsonl(
        claude / "history.jsonl",
        [
            {
                "display": "Repair the widget",
                "project": "/work/claude-project",
                "sessionId": "22222222-2222-2222-2222-222222222222",
                "timestamp": 1784343600000,
            }
        ],
    )
    settings = Settings(
        database_url=postgres_database_url,
        machine_id=UUID("11111111-2222-3333-4444-555555555555"),
        machine_name="pytest-machine",
        contributor="Test Contributor",
        data_dir=data,
        codex_root=codex,
        codex_history=codex / "history.jsonl",
        claude_root=claude,
        claude_history=claude / "history.jsonl",
        gemini_root=tmp_path / "gemini",
        git_root=tmp_path / "Projects",
    )
    return settings, codex_session, claude_session
