from __future__ import annotations

from dataclasses import dataclass

from chatreview.resume import ResumeRefreshSummary
from chatreview.summary_jobs import (
    SummaryRunManager,
    SummaryRunPlan,
    load_summary_agent,
)


@dataclass
class FakeProvider:
    model_name: str = "codex-cli"

    def generate_json(self, **_kwargs):
        return {}

    def close(self) -> None:
        pass


def test_summary_manager_persists_allowlisted_selection_and_result(monkeypatch, corpus) -> None:
    settings, _, _ = corpus
    messages = []

    class FakeRefresher:
        def __init__(self, _database_url, _model, *, progress):
            self.progress = progress

        def run(self, **kwargs):
            messages.append(kwargs)
            self.progress("Generated one bounded summary")
            return ResumeRefreshSummary(
                run_id=7,
                selected=1,
                generated=1,
                reused=0,
                skipped=0,
                failed=0,
                status="complete",
                model_name="codex-cli",
            )

    monkeypatch.setattr("chatreview.summary_jobs.ResumeSurfaceRefresher", FakeRefresher)
    manager = SummaryRunManager(
        settings,
        provider_factory=lambda _plan: FakeProvider(),
        state_path=settings.data_dir / "test-summary-run.json",
    )

    queued = manager.start(SummaryRunPlan(provider="codex-cli", days=7, limit=12))
    completed = manager.wait(2)

    assert queued["status"] in {"queued", "running", "complete"}
    assert completed["status"] == "complete"
    assert completed["result"]["generated"] == 1
    assert completed["active"] is False
    assert load_summary_agent(settings.data_dir) == "codex-cli"
    assert messages == [{"days": 7, "limit": 12, "per_project_limit": 3}]
    assert "owner_pid" not in completed


def test_summary_plan_rejects_unbounded_ranges() -> None:
    try:
        SummaryRunPlan(provider="qwen", days=0)
    except ValueError as exc:
        assert "between 1 and 365" in str(exc)
    else:
        raise AssertionError("invalid summary range was accepted")
