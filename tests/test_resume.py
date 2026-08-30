from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chatreview.api import create_app
from chatreview.db import database
from chatreview.ingest import Ingestor
from chatreview.providers import ClaudeAdapter, CodexAdapter
from chatreview.resume import (
    RESUME_REFRESH_LOCK,
    ModelUnavailable,
    ProviderResumeModel,
    ResumeDraft,
    ResumeError,
    ResumeSurfaceRefresher,
    list_resume_surfaces,
    select_work_groups,
)
from chatreview.summary_providers import SummaryProviderError


class FakeResumeModel:
    model_name = "test/qwen-27b"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.release_count = 0

    def generate(self, prompt: str) -> ResumeDraft:
        self.prompts.append(prompt)
        return ResumeDraft(
            concept="Restore the failing work path",
            long_term_goal="Make the affected project complete its intended workflow reliably.",
            summary=(
                "The thread reproduced the failure and captured a concrete error. "
                "No later verification proves that the underlying problem was fixed."
            ),
            current_state="ready",
            next_decision=None,
            next_moves=["Re-run the focused failing check from the recorded repository."],
            research_directions=["Inspect the latest error evidence before changing implementation."],
            open_loops=["The final successful verification is still missing."],
            confidence="high",
        )

    def release(self) -> None:
        self.release_count += 1


def _draft_payload(**overrides):
    payload = {
        "concept": "Resume the archive refresh",
        "long_term_goal": "Keep the multi-device conversation archive current and verifiable.",
        "summary": "The scheduled sync is still running and its final result has not been checked.",
        "current_state": "waiting",
        "next_decision": None,
        "next_moves": ["Wait for the active sync, then inspect its durable completion log."],
        "research_directions": [],
        "open_loops": ["The active sync has not produced a final exit status."],
        "confidence": "high",
    }
    payload.update(overrides)
    return payload


def test_resume_draft_normalizes_state_from_remaining_work() -> None:
    unfinished = ResumeDraft.model_validate(
        _draft_payload(current_state="done", next_moves=["Check the result later."])
    )
    assert unfinished.current_state == "ready"

    draft = ResumeDraft.model_validate(
        _draft_payload(
            current_state="done",
            next_moves=[],
            open_loops=[],
            summary="The work and its final verification are complete with no remaining follow-up.",
        )
    )
    assert draft.current_state == "done"

    decision = ResumeDraft.model_validate(
        _draft_payload(
            current_state="ready",
            next_decision="Should the remote changes be integrated during the active backfill?",
        )
    )
    assert decision.current_state == "decision"

    completed_with_placeholders = ResumeDraft.model_validate(
        _draft_payload(
            current_state="done",
            next_decision="No decision required; the work is complete.",
            next_moves=["No further action required."],
            open_loops=[],
            summary="The work and its final verification are complete with no remaining follow-up.",
        )
    )
    assert completed_with_placeholders.current_state == "done"
    assert completed_with_placeholders.next_decision is None
    assert completed_with_placeholders.next_moves == []


class FakeSummaryProvider:
    model_name = "local/qwen"

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.responses = iter(responses or [_draft_payload()])
        self.prompts: list[str] = []
        self.closed = False

    def generate_json(self, *, system_prompt, user_prompt, schema_name, schema):
        assert "untrusted evidence" in system_prompt
        assert schema_name == "resume_surface"
        assert schema["type"] == "object"
        self.prompts.append(user_prompt)
        return next(self.responses)

    def close(self) -> None:
        self.closed = True


def test_provider_model_retries_one_invalid_structured_response() -> None:
    provider = FakeSummaryProvider(
        [_draft_payload(current_state="waiting", next_moves=[]), _draft_payload()]
    )
    model = ProviderResumeModel(provider)

    draft = model.generate("UNTRUSTED_ARCHIVE_EVIDENCE_JSON")
    model.release()

    assert draft.current_state == "waiting"
    assert len(provider.prompts) == 2
    assert "VALIDATION_RETRY" in provider.prompts[1]
    assert provider.closed is True


def test_provider_model_maps_transport_errors_to_unavailable() -> None:
    class OfflineProvider(FakeSummaryProvider):
        def generate_json(self, **_kwargs):
            raise SummaryProviderError("endpoint is offline")

    with pytest.raises(ModelUnavailable, match="endpoint is offline"):
        ProviderResumeModel(OfflineProvider()).generate("evidence")


def test_resume_refresh_persists_grounded_surfaces_and_reuses_unchanged(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    model = FakeResumeModel()
    refresher = ResumeSurfaceRefresher(settings.database_url, model)

    first = refresher.run(days=365, limit=10, per_project_limit=2)

    assert first.status == "complete"
    assert first.generated == 2
    assert first.reused == 0
    assert model.release_count == 1
    assert all("UNTRUSTED_ARCHIVE_EVIDENCE_JSON" in prompt for prompt in model.prompts)
    assert any("frobnicator" in prompt for prompt in model.prompts)
    assert any("widget" in prompt for prompt in model.prompts)

    with database(settings.database_url, read_only=True) as connection:
        payload = list_resume_surfaces(connection)
    assert payload["total"] == 2
    assert payload["states"] == {"ready": 2}
    assert all(item["concept"] == "Restore the failing work path" for item in payload["surfaces"])
    assert all(item["locations"][0]["machine_name"] == "pytest-machine" for item in payload["surfaces"])
    assert {item["project_name"] for item in payload["surfaces"]} == {
        "codex-project",
        "claude-project",
    }

    response = TestClient(create_app(settings)).get("/api/resume-surfaces")
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["latest_run"]["model_name"] == "test/qwen-27b"
    assert "prompt_hash" not in response.json()["surfaces"][0]
    assert "evidence_fingerprint" not in response.json()["surfaces"][0]
    assert "machine_id" not in response.json()["surfaces"][0]["locations"][0]

    second = refresher.run(days=365, limit=10, per_project_limit=2)

    assert second.status == "complete"
    assert second.generated == 0
    assert second.reused == 2
    assert len(model.prompts) == 2
    assert model.release_count == 2


def test_resume_selection_can_be_bounded_to_recent_hours(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    with database(settings.database_url) as connection:
        session_ids = [
            int(row["id"])
            for row in connection.execute(
                "SELECT id FROM sessions WHERE provider<>'git' ORDER BY id"
            ).fetchall()
        ]
        connection.execute(
            "UPDATE sessions SET ended_at=clock_timestamp() WHERE id=?",
            (session_ids[0],),
        )
        connection.execute(
            "UPDATE sessions SET ended_at=clock_timestamp() - interval '7 hours' WHERE id=?",
            (session_ids[1],),
        )

    with database(settings.database_url, read_only=True) as connection:
        selected = select_work_groups(
            connection,
            days=30,
            hours=6,
            limit=10,
            per_project_limit=2,
        )

    assert [group.root.id for group in selected] == [session_ids[0]]


class FailingResumeModel(FakeResumeModel):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def generate(self, prompt: str) -> ResumeDraft:
        self.prompts.append(prompt)
        raise self.error


def test_resume_refresh_records_planned_and_unattempted_groups(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    model = FailingResumeModel(ModelUnavailable("model endpoint is offline"))

    summary = ResumeSurfaceRefresher(settings.database_url, model).run(
        days=365, limit=10, per_project_limit=2
    )

    assert summary.status == "failed"
    assert summary.selected == 2
    assert summary.failed == 1
    assert summary.skipped == 1
    with database(settings.database_url, read_only=True) as connection:
        run = connection.execute("SELECT * FROM resume_surface_runs WHERE id=?", (summary.run_id,)).fetchone()
    assert run["selected_count"] == 2
    assert run["skipped_count"] == 1
    assert run["completed_at"] is not None
    assert run["metadata_json"]["unattempted_count"] == 1
    assert len(run["metadata_json"]["unattempted_root_session_ids"]) == 1


def test_resume_refresh_finalizes_unexpected_failure_before_reraising(corpus) -> None:
    settings, _, _ = corpus
    Ingestor(
        settings,
        [CodexAdapter(settings.codex_root), ClaudeAdapter(settings.claude_root)],
    ).run()
    model = FailingResumeModel(RuntimeError("programming defect"))

    with pytest.raises(RuntimeError, match="programming defect"):
        ResumeSurfaceRefresher(settings.database_url, model).run(days=365, limit=10, per_project_limit=2)

    with database(settings.database_url, read_only=True) as connection:
        run = connection.execute("SELECT * FROM resume_surface_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert run["status"] == "failed"
    assert run["selected_count"] == 2
    assert run["failed_count"] == 1
    assert run["skipped_count"] == 1
    assert run["completed_at"] is not None
    assert run["metadata_json"]["errors"][0]["type"] == "RuntimeError"
    assert model.release_count == 1


def test_resume_refresh_refuses_an_overlapping_database_lease(corpus) -> None:
    settings, _, _ = corpus
    model = FakeResumeModel()

    with (
        database(settings.database_url) as connection,
        connection.advisory_lock(RESUME_REFRESH_LOCK),
        pytest.raises(ResumeError, match="already running"),
    ):
        ResumeSurfaceRefresher(settings.database_url, model).run()

    with database(settings.database_url, read_only=True) as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM resume_surface_runs").fetchone()["count"]
    assert count == 0
