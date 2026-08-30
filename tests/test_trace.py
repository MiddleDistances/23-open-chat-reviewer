from __future__ import annotations

from fastapi.testclient import TestClient

from chatreview.api import create_app
from chatreview.db import database
from chatreview.episodes import EpisodeBuilder
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.trace import build_session_trace, normalize_call


def _prepare(corpus):
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    EpisodeBuilder(settings).run()
    return settings


def test_normalize_call_uses_provider_neutral_actions() -> None:
    assert normalize_call("apply_patch", "patch") == ("edit", "edit:patch")
    assert normalize_call("exec_command", '{"cmd":"uv run pytest -q"}') == (
        "test",
        "test:pytest",
    )
    assert normalize_call("Bash", '{"command":"psql -d local"}') == (
        "database",
        "database:psql",
    )
    assert normalize_call("WebSearch", "query") == ("research", "research:web-search")
    assert normalize_call(
        "exec",
        'const result = await tools.exec_command({ cmd: "uv run pytest -q" });',
    ) == ("test", "test:pytest")


def test_session_trace_projects_occurrences_and_exact_calls(corpus) -> None:
    settings = _prepare(corpus)
    with database(settings.database_url, read_only=True) as connection:
        session_id = int(
            connection.execute("SELECT id FROM sessions WHERE provider='codex'").fetchone()["id"]
        )
        trace = build_session_trace(connection, session_id)

    assert trace is not None
    assert trace["session"]["external_id"] == "11111111-1111-1111-1111-111111111111"
    assert trace["summary"]["occurrences"] == 1
    assert trace["summary"]["tool_calls"] == 1
    assert trace["summary"]["error_occurrences"] == 1
    assert trace["occurrences"][0]["signature"]["basis"] == "observed-error"
    assert trace["occurrences"][0]["signature"]["provisional"] is True
    assert trace["occurrences"][0]["call_runs"][0]["operation"] == "execute:python"
    assert trace["occurrences"][0]["call_runs"][0]["outcome"] == "error"


def test_session_trace_api_returns_404_for_unknown_session(corpus) -> None:
    settings = _prepare(corpus)
    client = TestClient(create_app(settings))
    response = client.get("/api/sessions/999999/trace")
    assert response.status_code == 404
