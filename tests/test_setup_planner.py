from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from chatreview.setup_planner import (
    CorpusStats,
    DatabaseHealth,
    DatabaseSnapshot,
    HistoryScope,
    MachineNode,
    ReasoningFootprint,
    ScopeEstimate,
    SemanticPolicy,
    SetupPlan,
    SetupPlanner,
)

MACHINE_ID = UUID("11111111-2222-3333-4444-555555555555")


def _settings(tmp_path: Path) -> SimpleNamespace:
    codex = tmp_path / "codex"
    claude = tmp_path / "claude"
    gemini = tmp_path / "gemini"
    git = tmp_path / "Projects"
    codex.mkdir()
    claude.mkdir()
    (codex / "history.jsonl").write_bytes(b"history\n")
    return SimpleNamespace(
        database_url="postgresql://archive:secret@example.test/chatreview",
        machine_id=MACHINE_ID,
        machine_name="workstation",
        codex_root=codex,
        codex_history=codex / "history.jsonl",
        claude_root=claude,
        claude_history=claude / "history.jsonl",
        gemini_root=gemini,
        git_root=git,
    )


def _snapshot() -> DatabaseSnapshot:
    return DatabaseSnapshot(
        health=DatabaseHealth(
            available=True,
            schema_version=11,
            ingestion_complete=4,
            ingestion_in_progress=1,
            ingestion_failed=0,
        ),
        corpus=CorpusStats(
            database_size_bytes=1024**3,
            table_storage_bytes={"contents": 900},
            sources=4,
            source_revisions=5,
            raw_records=10,
            raw_payloads=9,
            sessions=3,
            events=25,
            contents=20,
            text_units=30,
            artifacts=7,
            episodes=2,
            annotations=1,
            parse_errors=1,
            source_bytes=500,
            indexed_bytes=450,
            first_event_at=datetime(2025, 1, 1, tzinfo=UTC),
            last_event_at=datetime(2026, 1, 1, tzinfo=UTC),
            providers={"claude": 1, "codex": 2},
            source_status={"complete": 4, "ingesting": 1},
        ),
        reasoning=ReasoningFootprint(
            raw_reasoning_records=10,
            raw_reasoning_bytes=1000,
            encrypted_reasoning_records=8,
            encrypted_reasoning_bytes=800,
            readable_reasoning_units=2,
            readable_reasoning_bytes=120,
            opaque_artifact_count=1,
            opaque_artifact_bytes=100,
            semantic_windows_total=5,
            semantic_reasoning_windows=1,
        ),
        machines=(
            MachineNode(
                machine_id=str(MACHINE_ID),
                name="workstation",
                first_seen_at=datetime(2025, 1, 1, tzinfo=UTC),
                last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                source_count=4,
                session_count=3,
                event_count=25,
            ),
        ),
        semantic_runs=(),
    )


class FakeDatabase:
    def __init__(self) -> None:
        self.scopes: list[tuple[HistoryScope, tuple[str, ...]]] = []

    def snapshot(self) -> DatabaseSnapshot:
        return _snapshot()

    def estimate_scope(self, scope: HistoryScope, providers: tuple[str, ...]) -> ScopeEstimate:
        self.scopes.append((scope, providers))
        return ScopeEstimate(
            available=True,
            start=scope.start,
            end=scope.end,
            providers=providers,
            events=12,
            sessions=2,
            text_units=16,
            raw_records=9,
            raw_bytes=850,
            included_percent=48.0,
        )


def test_plan_validates_provider_and_date_scope() -> None:
    plan = SetupPlan(
        providers=("codex", "claude"),
        history=HistoryScope(start=date(2025, 1, 1), end=date(2025, 3, 31)),
        semantic=SemanticPolicy(include_reasoning=True),
    )

    assert plan.providers == ("codex", "claude")
    assert plan.history.start == date(2025, 1, 1)
    assert plan.semantic.include_reasoning is True

    with pytest.raises(ValueError, match="unsupported provider"):
        SetupPlan(providers=("codex", "wat"))
    with pytest.raises(ValueError, match="start date"):
        HistoryScope(start=date(2025, 4, 1), end=date(2025, 3, 31))
    with pytest.raises(ValueError, match="at least one provider"):
        SetupPlan(providers=())


def test_preview_discovers_roots_without_writing_and_keeps_secret_out(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    database = FakeDatabase()
    planner = SetupPlanner(settings, database=database)
    plan = SetupPlan(
        providers=("codex", "claude"),
        history=HistoryScope(start=date(2025, 1, 1), end=date(2025, 12, 31)),
        semantic=SemanticPolicy(include_reasoning=False, include_encoded_reasoning=False),
    )

    preview = planner.preview(plan)
    payload = preview.to_dict()

    assert payload["machine"]["id"] == str(MACHINE_ID)
    assert payload["corpus"]["events"] == 25
    assert payload["reasoning"]["encrypted_reasoning_bytes"] == 800
    assert payload["scope_estimate"]["events"] == 12
    assert database.scopes == [(plan.history, plan.providers)]
    assert payload["plan"]["semantic"]["include_reasoning"] is False
    assert "secret" not in repr(payload)
    assert not (tmp_path / "state").exists()

    roots = {item["provider"]: item for item in payload["roots"]}
    assert roots["codex"]["exists"] is True
    assert roots["codex"]["history_exists"] is True
    assert roots["claude"]["history_exists"] is False
    assert roots["gemini"]["exists"] is False


def test_preview_warns_that_encoded_reasoning_is_not_vector_text(tmp_path: Path) -> None:
    planner = SetupPlanner(_settings(tmp_path), database=FakeDatabase())
    preview = planner.preview(
        SetupPlan(semantic=SemanticPolicy(include_reasoning=True, include_encoded_reasoning=True))
    )

    assert any("encoded reasoning" in warning.lower() for warning in preview.warnings)
    assert any("raw evidence" in warning.lower() for warning in preview.warnings)


def test_status_is_read_only_and_degrades_without_database(tmp_path: Path) -> None:
    class BrokenDatabase:
        def snapshot(self) -> DatabaseSnapshot:
            raise RuntimeError("postgresql://user:password@host/db should not escape")

        def estimate_scope(self, scope: HistoryScope, providers: tuple[str, ...]) -> ScopeEstimate:
            raise AssertionError("status must not estimate scope")

    status = SetupPlanner(_settings(tmp_path), database=BrokenDatabase()).status()
    payload = status.to_dict()

    assert payload["database"]["available"] is False
    assert payload["database"]["error"] == "RuntimeError"
    assert "password" not in repr(payload)
    assert payload["roots"]


def test_history_scope_serializes_as_half_open_dates() -> None:
    scope = HistoryScope.from_values("2026-07-01", "2026-07-31")

    assert scope.to_dict() == {
        "start": "2026-07-01",
        "end": "2026-07-31",
        "mode": "range",
    }
    assert HistoryScope().to_dict()["mode"] == "all"
