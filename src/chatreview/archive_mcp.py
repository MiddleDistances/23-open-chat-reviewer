"""Small read-only MCP interface for recalling archived work.

The public MCP seam intentionally exposes useful archive questions, not database
implementation details. Every operation opens a transactionally read-only session
and clamps its result size before returning it to an agent.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from chatreview.db import database
from chatreview.resume import list_resume_surfaces
from chatreview.search import SearchFilters, corpus_stats, lexical_search, list_sessions
from chatreview.trace import build_session_trace


class ArchiveReader:
    """Bounded, read-only questions an agent may ask of the archive."""

    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("CHATREVIEW_DATABASE_URL is required")
        self._database_url = database_url

    def status(self) -> dict[str, Any]:
        """Return source and record counts without exposing configuration secrets."""

        with database(self._database_url, read_only=True) as connection:
            return _jsonable(corpus_stats(connection))

    def search(
        self,
        query: str,
        *,
        provider: str | None = None,
        project: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search exact archived text with session and source provenance."""

        with database(self._database_url, read_only=True) as connection:
            result = lexical_search(
                connection,
                query,
                filters=SearchFilters(
                    provider=provider,
                    project=project,
                    date_from=date_from,
                    date_to=date_to,
                    include_reasoning=False,
                ),
                limit=min(max(limit, 1), 50),
            )
        return _jsonable(result)

    def sessions(
        self,
        *,
        provider: str | None = None,
        project: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find recent conversations by provider, project, title, or working path."""

        with database(self._database_url, read_only=True) as connection:
            result = list_sessions(
                connection,
                provider=provider,
                project=project,
                query=query,
                limit=min(max(limit, 1), 50),
            )
        return _jsonable(result)

    def trace(self, session_id: int) -> dict[str, Any] | None:
        """Return one bounded chronological evidence trace by numeric session ID."""

        with database(self._database_url, read_only=True) as connection:
            result = build_session_trace(
                connection,
                session_id,
                occurrence_limit=120,
                run_limit=80,
            )
        return _jsonable(result)

    def recent_work(self, limit: int = 20) -> dict[str, Any]:
        """Return recent model-authored resume cards, clearly separated from raw facts."""

        with database(self._database_url, read_only=True) as connection:
            result = list_resume_surfaces(connection, limit=min(max(limit, 1), 50))
        return _jsonable(result)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value


def main() -> None:
    """Launch the optional local stdio MCP server."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("MCP support is not installed. Run: uv sync --extra mcp") from exc

    database_url = os.environ.get("CHATREVIEW_DATABASE_URL", "").strip()
    reader = ArchiveReader(database_url)
    server = FastMCP(
        "Open Chat Reviewer",
        instructions=(
            "Read-only recall for archived Codex, Claude, Gemini, and Git work. "
            "Search results and traces are archive evidence. recent_work contains optional "
            "model-authored guidance and must be checked against its linked session trace."
        ),
        json_response=True,
    )
    server.tool(name="archive_status")(reader.status)
    server.tool(name="search_archive")(reader.search)
    server.tool(name="find_conversations")(reader.sessions)
    server.tool(name="get_conversation_trace")(reader.trace)
    server.tool(name="get_recent_work")(reader.recent_work)
    server.run()


if __name__ == "__main__":
    main()
