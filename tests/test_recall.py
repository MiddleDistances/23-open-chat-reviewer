"""Evidence-preservation and response-budget regressions for compact recall."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

from chatreview.archive_mcp import ArchiveReader
from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.recall import compact_response, dedupe_candidates, serialized_size


def candidate(event=1, unit="u1", text="exit 1", **extra):
    """Build one sanitized search candidate with independent event/unit identity."""
    return {"event_id": event, "event_key": f"e{event}", "session_id": event,
            "unit_key": unit, "text": text, "snippet": "same displayed snippet",
            "role": None, "kind": "tool-output", "provider": "codex",
            "timestamp": "2026-01-01T00:00:00Z", "source_path": "/synthetic/source",
            "raw_record_id": event, "provenance_hash": "a" * 64, **extra}


def test_exact_duplicate_uses_newest_source_without_reordering_other_groups():
    rows = [candidate(), candidate(2, text="different"),
            candidate(3, timestamp="2026-02-01T00:00:00Z")]
    groups = dedupe_candidates(rows)
    assert [g["row"]["event_id"] for g in groups] == [3, 2]
    assert len(groups[0]["copies"]) == 2
    card = compact_response(rows, query="exit")["conversations"][0]["anchors"][0]
    assert card["duplicates_collapsed"] == 1
    assert card["alternate_references"][0]["event_id"] == 1


def test_complete_copy_beats_newer_prefix_of_same_event_and_unit():
    full = candidate(text="Four failed tests: alpha beta gamma delta")
    prefix = candidate(text="Four failed tests:", timestamp="2026-04-01T00:00:00Z")
    assert dedupe_candidates([prefix, full])[0]["row"]["text"] == full["text"]


@pytest.mark.parametrize("left,right", [
    ("exit 0", "exit 1"), ("4 failed", "3 failed"),
    ("    CaseSensitive()", "CaseSensitive()"), ("Thing()", "thing()"),
])
def test_changed_receipts_and_code_are_not_deduplicated(left, right):
    assert len(dedupe_candidates([candidate(text=left), candidate(2, text=right)])) == 2


def test_shared_snippet_does_not_merge_different_content_or_distinct_units():
    assert len(dedupe_candidates([candidate(), candidate(2, text="different")])) == 2
    assert len(dedupe_candidates([candidate(), candidate(unit="u2")])) == 2
    assert len(dedupe_candidates([candidate(unit=None), candidate(unit=None)])) == 2
    assert len(dedupe_candidates([candidate(), candidate(2, timestamp="2026-02-01T00:00:00Z"),
                                  candidate(unit="u2")])) == 2
    assert len(dedupe_candidates([candidate(event_key=None, event_id=None, text="exit"),
                                  candidate(event_key=None, event_id=None, text="exit 1")])) == 2


def test_missing_timestamps_and_ties_are_deterministic():
    groups = dedupe_candidates([candidate(timestamp=None), candidate(2, timestamp=None)])
    assert groups[0]["row"]["event_id"] == 2


def test_unicode_and_metadata_are_included_in_total_budget():
    rows = [candidate(i, text=f"unique {i}", snippet="🦎" * 4000,
                      source_path="界" * 2000) for i in range(1, 20)]
    response = compact_response(rows, query="needle", budget=3000)
    assert serialized_size(response) <= 3000
    assert response["returned_anchors"] >= 1
    assert response["response_truncated"]
    assert response["conversations"][0]["anchors"][0]["snippet_truncated"]
    assert response["conversations"][0]["anchors"][0]["metadata_truncated"]
    response = compact_response([], query="🦎" * 4000, budget=1000)
    assert serialized_size(response) <= 1000
    assert response["error"] == "metadata_exceeds_budget"


def test_empty_candidates_cap_and_unknown_outcomes_are_explicit():
    empty = compact_response([], query="absent")
    assert empty["returned_anchors"] == 0
    assert not empty["candidate_limit_reached"]
    response = compact_response([candidate(text="Deployment completed!")], query="deploy",
                                candidate_limit=1)
    assert response["candidate_limit_reached"] and response["more_results_may_exist"]
    card = response["conversations"][0]["anchors"][0]
    assert card["source_status"] == "unknown"
    assert "outcome" not in card


def test_discovery_and_context_preserve_original_receipts_and_legacy_tools(corpus):
    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root),
                       ClaudeAdapter(settings.claude_root)]).run()
    reader = ArchiveReader(settings.database_url)
    discovery = reader.find_prior_work("frobnicator", limit=1)
    assert serialized_size(discovery) <= 12000
    card = discovery["conversations"][0]["anchors"][0]
    assert card["provenance_hash"] and card["raw_record_id"]
    assert card["source_status"] in {"complete", "partial", "failed"}
    assert "text" not in card and "<mark>" not in card["snippet"]
    context = reader.read_prior_work(card["session_id"], card["anchor_event_id"])
    assert serialized_size(context) <= 16000
    assert any("frobnicator" in item["text"] for item in context["events"])
    timestamps = [item["timestamp"] for item in context["events"] if item["timestamp"]]
    assert timestamps == sorted(timestamps)
    assert any("Fatal error" in item["text"] for item in context["events"])
    with pytest.raises(ValueError, match="does not belong"):
        reader.read_prior_work(-1, card["anchor_event_id"])
    with pytest.raises(ValueError, match="unit_key"):
        reader.read_prior_work(card["session_id"], card["anchor_event_id"], unit_key="other")
    assert reader.search("frobnicator")[0]["text"]
    assert reader.sessions()
    assert reader.status()["sessions"] >= 1
    assert reader.trace(card["session_id"])["session"]["id"] == card["session_id"]
    assert isinstance(reader.recent_work(), dict)
    with database(settings.database_url, read_only=True) as connection:
        assert connection.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
        with pytest.raises(Exception, match="read-only"):
            connection.execute("DELETE FROM machines")


def test_partial_status_large_anchor_continuation_and_unit_paging(corpus):
    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root)]).run()
    reader = ArchiveReader(settings.database_url)
    hit = reader.search("Fatal error", limit=1)[0]
    with database(settings.database_url) as connection:
        connection.execute("UPDATE source_revisions SET status='partial' WHERE id=("
                           "SELECT source_revision_id FROM events WHERE id=?)", (hit["event_id"],))
        text = "Critical: 4 failed. " + "🦎" * 40000
        connection.execute("UPDATE contents SET text=?, char_count=? WHERE id=?",
                           (text, len(text), hit["content_id"]))
        connection.commit()
    context = reader.read_prior_work(hit["session_id"], hit["event_id"],
                                     unit_key=hit["unit_key"], before=0, after=0)
    assert serialized_size(context) <= 16000
    item = context["events"][0]
    assert item["source_status"] == "partial"
    assert item["text"].startswith("Critical: 4 failed.")
    assert item["text_truncated"] and item["next_read"]
    target = dict(item["next_read"])
    following = reader.read_prior_work(**target)
    assert following["events"][0]["text_offset"] == len(item["text"])
    assert following["events"][0]["text"]
    with pytest.raises(ValueError):
        reader.read_prior_work(hit["session_id"], hit["event_id"], text_offset=-1)


def test_new_tools_are_registered_alongside_legacy_tools(monkeypatch):
    fastmcp = pytest.importorskip("mcp.server.fastmcp")

    from chatreview import archive_mcp

    names = []

    class Server:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *, name):
            names.append(name)
            return lambda function: function

        def run(self):
            pass

    monkeypatch.setattr(fastmcp, "FastMCP", Server)
    monkeypatch.setenv("CHATREVIEW_DATABASE_URL", "postgresql:///synthetic")
    archive_mcp.main()
    assert set(names) == {"archive_status", "search_archive", "find_conversations",
                          "get_conversation_trace", "get_recent_work",
                          "find_prior_work", "read_prior_work"}


def test_multi_unit_event_has_explicit_unit_paging_and_selected_anchor(corpus):
    settings, codex_path, _ = corpus
    record = {"timestamp": "2026-07-18T02:00:04Z", "type": "response_item",
              "payload": {"type": "message", "role": "assistant", "content": [
                  {"type": "output_text", "text": f"Receipt unit {i}: exit {i}"}
                  for i in range(7)]}}
    with codex_path.open("ab") as handle:
        handle.write(json.dumps(record).encode() + b"\n")
    Ingestor(settings, [CodexAdapter(settings.codex_root)]).run()
    reader = ArchiveReader(settings.database_url)
    hit = reader.search("Receipt", limit=1)[0]
    context = reader.read_prior_work(hit["session_id"], hit["event_id"], before=0, after=0)
    assert len(context["events"]) == 3
    assert context["unit_continuations"][0]["unit_offset"] == 3
    next_page = reader.read_prior_work(**context["unit_continuations"][0])
    assert len(next_page["events"]) == 3
    assert next_page["events"][0]["unit_key"] != context["events"][0]["unit_key"]
    last_page = reader.read_prior_work(**next_page["unit_continuations"][0])
    assert len(last_page["events"]) == 1
    chosen = reader.read_prior_work(hit["session_id"], hit["event_id"],
                                   unit_key=last_page["events"][0]["unit_key"], before=0, after=0)
    assert chosen["events"][0]["text"] == "Receipt unit 6: exit 6"


def test_null_timestamp_neighbors_match_chronological_trace_order(corpus):
    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root)]).run()
    reader = ArchiveReader(settings.database_url)
    hit = reader.search("Fatal error", limit=1)[0]
    with database(settings.database_url) as connection:
        connection.execute("UPDATE events SET timestamp=NULL WHERE id=?", (hit["event_id"],))
        connection.commit()
    context = reader.read_prior_work(hit["session_id"], hit["event_id"], before=3, after=3)
    assert context["events"][0]["event_id"] == hit["event_id"]
    assert context["events"][0]["timestamp"] is None


def test_stdio_client_can_discover_and_read_compact_evidence(corpus):
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    settings, _, _ = corpus
    Ingestor(settings, [CodexAdapter(settings.codex_root)]).run()

    async def verify():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "chatreview.archive_mcp"],
            env={**os.environ, "CHATREVIEW_DATABASE_URL": settings.database_url},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert len(names) == 7
            discovery = await client.call_tool("find_prior_work", {"query": "frobnicator", "limit": 1})
            assert not discovery.isError
            envelope = json.loads(discovery.content[0].text)
            assert serialized_size(envelope) <= 12000
            target = dict(envelope["conversations"][0]["anchors"][0]["read_target"])
            target.pop("tool")
            context = await client.call_tool("read_prior_work", target)
            assert not context.isError
            assert serialized_size(json.loads(context.content[0].text)) <= 16000
            mismatch = await client.call_tool("read_prior_work", {**target, "session_id": -1})
            assert mismatch.isError

    asyncio.run(verify())
