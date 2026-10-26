"""Read OpenCode SQLite evidence through deterministic, private session exports.

The source database is opened read-only, including its live WAL. A single read
transaction supplies each export cycle. Exact SQLite row values (including the
original JSON strings) are retained; byte offsets refer to the generated export,
not to SQLite pages. Credentials, diagnostics and snapshot repositories are excluded.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

import orjson

from chatreview.providers.base import (
    ProviderAdapter,
    add_fragment,
    extract_common_artifacts,
    normalize_adapter_roots,
    stable_hash,
)
from chatreview.types import Artifact, ParsedRecord, SourceSpec, TextFragment


class OpenCodeAdapter(ProviderAdapter):
    """Archive current OpenCode session/message/part tables without source writes."""

    name = "opencode"
    parser_version = 1

    def __init__(self, root: Path | Iterable[Path], archive_root: Path) -> None:
        self.roots = normalize_adapter_roots(root)
        self.archive_root = archive_root.expanduser().resolve()

    def prepare(self) -> list[SourceSpec]:
        """Atomically refresh exports; unchanged sessions retain their mtime."""
        self.archive_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.archive_root / ".export.lock").open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            sources = []
            for root in self.roots:
                database = root / "opencode.db"
                if not database.is_file() or database.is_symlink():
                    continue
                with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("PRAGMA query_only=ON")
                    connection.execute("BEGIN")
                    for session in connection.execute("SELECT * FROM session ORDER BY id"):
                        session = dict(session)
                        sid = session["id"]
                        payload = {
                            "schema": "chatreview.opencode.v1",
                            "database": str(database),
                            "session": session,
                            "messages": [
                                dict(row)
                                for row in connection.execute(
                                    "SELECT * FROM message WHERE session_id=? ORDER BY time_created,id",
                                    (sid,),
                                )
                            ],
                            "parts": [
                                dict(row)
                                for row in connection.execute(
                                    "SELECT * FROM part WHERE session_id=? ORDER BY time_created,id", (sid,)
                                )
                            ],
                        }
                        path = self.archive_root / f"{stable_hash(str(database) + ':' + sid)}.json"
                        _write_if_changed(path, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))
                        sources.append(
                            {
                                "path": str(path),
                                "provenance": {
                                    "database": str(database),
                                    "session_id": sid,
                                    "format": "sqlite-row-export",
                                    "source_root": str(root),
                                },
                            }
                        )
            _write_if_changed(self.archive_root / "catalog.json", orjson.dumps(sources))
        return self.discover()

    def discover(self) -> list[SourceSpec]:
        """Read the prepared catalog without opening or exporting the live database."""
        catalog = self.archive_root / "catalog.json"
        if not catalog.is_file():
            return []
        roots = {str(root / "opencode.db") for root in self.roots}
        return [
            SourceSpec(self.name, Path(item["path"]), "session", item["provenance"])
            for item in orjson.loads(catalog.read_bytes())
            if item["provenance"]["database"] in roots and Path(item["path"]).is_file()
        ]

    def record_format(self, source: SourceSpec) -> Literal["json-document"]:
        return "json-document"

    def parse(self, data: dict[str, Any], source: SourceSpec) -> ParsedRecord:
        raise ValueError("OpenCode session exports contain multiple events; use parse_many")

    def parse_many(self, data: Any, source: SourceSpec) -> list[ParsedRecord]:
        """Project persisted messages and parts, preserving tool status and parent IDs."""
        if not isinstance(data, dict) or data.get("schema") != "chatreview.opencode.v1":
            raise ValueError("unsupported OpenCode export")
        session = data["session"]
        common = dict(
            provider=self.name,
            session_external_id=session["id"],
            parent_session_external_id=session.get("parent_id"),
            cwd=session.get("directory"),
            project=session.get("directory"),
        )
        records = [
            ParsedRecord(
                **common,
                event_type="session_meta",
                timestamp=str(session["time_created"]),
                metadata={
                    "title": session.get("title"),
                    "project_id": session.get("project_id"),
                    "database": data["database"],
                },
            )
        ]
        parts: dict[str, list[dict]] = {}
        for row in data["parts"]:
            parts.setdefault(row["message_id"], []).append(row)
        for message in data["messages"]:
            info = orjson.loads(message["data"])
            role = info.get("role")
            fragments: list[TextFragment] = []
            artifacts: list[Artifact] = []
            part_types = []
            for row in parts.get(message["id"], []):
                part = orjson.loads(row["data"])
                kind = part.get("type")
                part_types.append(kind)
                if kind in {"text", "reasoning"}:
                    add_fragment(
                        fragments,
                        artifacts,
                        kind="reasoning" if kind == "reasoning" else f"{role}-message",
                        value=part.get("text"),
                    )
                elif kind == "tool":
                    state = part.get("state", {})
                    label = part.get("tool")
                    add_fragment(
                        fragments, artifacts, kind="tool-input", value=state.get("input"), label=label
                    )
                    add_fragment(
                        fragments,
                        artifacts,
                        kind="tool-output",
                        value=state.get("error") if state.get("status") == "error" else state.get("output"),
                        label=label,
                        is_error=state.get("status") == "error",
                    )
                    if label:
                        artifacts.append(Artifact("tool", label))
                elif kind == "file":
                    add_fragment(
                        fragments,
                        artifacts,
                        kind="attachment",
                        value=part.get("filename"),
                        label=part.get("mime"),
                    )
            records.append(
                ParsedRecord(
                    **common,
                    event_type="message",
                    role=role,
                    timestamp=str(info.get("time", {}).get("created", message["time_created"])),
                    provider_event_id=message["id"],
                    parent_event_id=info.get("parentID"),
                    metadata={
                        "model": info.get("modelID") or info.get("model"),
                        "agent": info.get("agent"),
                        "part_types": part_types,
                    },
                    fragments=fragments,
                    artifacts=extract_common_artifacts(fragments, artifacts),
                )
            )
        return records


def _write_if_changed(path: Path, payload: bytes) -> None:
    """Replace a complete private export and preserve unchanged file identity."""
    if path.is_file() and path.read_bytes() == payload:
        return
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
