from __future__ import annotations

from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.semantic import (
    DeriveOptions,
    SemanticDeriver,
    SemanticDocumentBuilder,
    SemanticPolicy,
    _semantic_policy_clause,
    semantic_policy_from_dict,
    semantic_policy_to_dict,
)


def _rows() -> list[dict[str, object]]:
    return [
        {
            "event_id": 1,
            "role": "assistant",
            "event_type": "message",
            "kind": "context-summary",
            "text": "The same old context summary repeated for every window.",
            "provider": "codex",
            "project": "archive",
            "timestamp": "2026-08-01T09:00:00Z",
        },
        {
            "event_id": 2,
            "role": "user",
            "event_type": "message",
            "kind": "user-message",
            "text": "Investigate the distinct database migration failure in this session.",
            "provider": "codex",
            "project": "archive",
            "timestamp": "2026-08-01T09:01:00Z",
        },
        {
            "event_id": 3,
            "role": "assistant",
            "event_type": "message",
            "kind": "reasoning",
            "text": "I should compare the migration log with the schema revision.",
            "provider": "codex",
            "project": "archive",
            "timestamp": "2026-08-01T09:02:00Z",
        },
        {
            "event_id": 4,
            "role": "assistant",
            "event_type": "message",
            "kind": "reasoning-summary",
            "text": "Reasoning summary: migration revision mismatch.",
            "provider": "codex",
            "project": "archive",
            "timestamp": "2026-08-01T09:03:00Z",
        },
        {
            "event_id": 5,
            "role": "assistant",
            "event_type": "tool-call",
            "kind": "tool-input",
            "text": "psql -c SELECT version();",
            "provider": "codex",
            "project": "archive",
            "timestamp": "2026-08-01T09:04:00Z",
        },
    ]


def test_default_policy_keeps_existing_conversation_scope() -> None:
    policy = SemanticPolicy()

    assert policy.include_reasoning is True
    assert policy.include_reasoning_summaries is False
    assert policy.include_tool_content is False
    assert policy.include_context is True
    assert "reasoning" in policy.kinds
    assert "reasoning-summary" not in policy.kinds
    assert "tool-input" not in policy.kinds
    assert "context-summary" in policy.kinds


def test_policy_round_trip_and_sql_clause_are_stable() -> None:
    policy = SemanticPolicy(
        include_reasoning=False,
        include_reasoning_summaries=True,
        include_tool_content=True,
        include_context=False,
        providers=("codex", "claude"),
        projects=("archive",),
        date_from="2026-08-01",
        date_to="2026-08-31",
    )

    restored = semantic_policy_from_dict(semantic_policy_to_dict(policy))

    assert restored == policy
    clause = _semantic_policy_clause(policy)
    assert "reasoning-summary" in clause
    assert "tool-input" in clause
    assert "context-summary" not in clause
    assert "reasoning'" not in clause


def test_builder_excludes_optional_kinds_and_applies_scope() -> None:
    policy = SemanticPolicy(
        include_reasoning=False,
        include_reasoning_summaries=False,
        include_tool_content=True,
        include_context=False,
        providers=("codex",),
        projects=("archive",),
        date_from="2026-08-01",
        date_to="2026-08-01",
    )

    rows = SemanticDocumentBuilder(policy).build_segments(_rows(), max_chars=400)
    event_ids = [segment["event_id"] for segment in rows]

    assert event_ids == [2, 5]
    assert all("context" not in segment["text"].lower() for segment in rows)
    assert all("reasoning" not in segment["text"].lower() for segment in rows)


def test_preview_uses_distinct_vectorized_message_not_repeated_context() -> None:
    builder = SemanticDocumentBuilder(SemanticPolicy())
    windows = builder.build_windows(_rows(), max_chars=400, overlap_events=0)

    assert windows
    preview = windows[0]["preview"]
    assert "Investigate the distinct database migration failure" in preview
    assert "same old context summary" not in preview
    assert preview in windows[0]["text"]


def test_preview_falls_back_to_document_text_for_legacy_windows() -> None:
    builder = SemanticDocumentBuilder(SemanticPolicy())

    preview = builder.preview("[assistant]\nA useful legacy window body", max_chars=20)

    assert preview == "A useful legacy wind"


def test_deriver_applies_policy_scope_before_windowing(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        run = connection.execute(
            """
            INSERT INTO semantic_runs(
                run_key, model_name, model_revision, dimensions, window_chars,
                overlap_events, profile, corpus_fingerprint, derivation_version,
                status, config_json
            ) VALUES (
                'policy-build-test', 'test', 'test', 512, 1000, 0, 'conversation',
                'fingerprint', 1, 'building', '{}'
            ) RETURNING id
            """
        ).fetchone()
        assert run is not None
        policy = SemanticPolicy(
            providers=("codex",),
            date_from="2026-07-18",
            date_to="2026-07-18",
        )
        count = SemanticDeriver(settings)._build_windows(
            connection,
            int(run["id"]),
            DeriveOptions(window_chars=1_000, overlap_events=0, policy=policy),
            policy=policy,
        )
        rows = connection.execute(
            """
            SELECT s.provider
            FROM semantic_windows w JOIN sessions s ON s.id=w.session_id
            WHERE w.run_id=?
            """,
            (run["id"],),
        ).fetchall()

    assert count > 0
    assert {row["provider"] for row in rows} == {"codex"}
