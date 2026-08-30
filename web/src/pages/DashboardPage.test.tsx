import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "./DashboardPage";

const response = {
  surfaces: [
    {
      id: 1,
      root_session_id: 41,
      concept: "Finish the active archive synchronization",
      long_term_goal: "Keep every device represented in one current PostgreSQL archive.",
      summary: "The Mac sync is still scanning repositories and has no final exit status.",
      current_state: "waiting",
      next_decision: null,
      next_moves: ["Wait for the sync, then verify its durable log."],
      research_directions: [],
      open_loops: ["The final source counts have not been checked."],
      confidence: "high",
      last_activity_at: "2026-08-28T12:53:13Z",
      generated_at: "2026-08-28T15:07:17Z",
      project_name: "23-chatReviewer",
      repository_url: "https://github.com/example/open-chat-reviewer",
      locations: [
        {
          session_id: 41,
          provider: "codex",
          cwd: "/Users/michael/Projects/23-chatReviewer",
          active_at: "2026-08-28T12:53:13Z",
          machine_name: "Michael's MacBook Pro",
          project_name: "23-chatReviewer",
          repository_url: "https://github.com/example/open-chat-reviewer",
        },
      ],
      providers: ["codex"],
    },
    {
      id: 2,
      root_session_id: 52,
      concept: "Completed evidence migration",
      long_term_goal: "Move the archive without losing source provenance.",
      summary: "Migration and final verification both completed.",
      current_state: "done",
      next_decision: null,
      next_moves: [],
      research_directions: [],
      open_loops: [],
      confidence: "high",
      last_activity_at: "2026-08-27T12:00:00Z",
      generated_at: "2026-08-28T15:07:17Z",
      project_name: "archive",
      repository_url: null,
      locations: [],
      providers: ["claude"],
    },
  ],
  total: 2,
  states: { waiting: 1, done: 1 },
  latest_run: {
    id: 3,
    model_name: "qwen",
    prompt_version: "resume-surface-v2",
    selected_count: 2,
    generated_count: 2,
    reused_count: 0,
    skipped_count: 0,
    failed_count: 0,
    status: "complete",
    started_at: "2026-08-28T15:00:00Z",
    completed_at: "2026-08-28T15:01:00Z",
  },
  method_note: "Locations are archive facts; summaries are derived guidance.",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("resume dashboard", () => {
  it("shows open work first and links each card to its root evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => response,
    }));

    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(await screen.findByText("Finish the active archive synchronization")).toBeInTheDocument();
    expect(screen.queryByText("Completed evidence migration")).not.toBeInTheDocument();
    expect(screen.getByText("Michael's MacBook Pro")).toBeInTheDocument();
    expect(screen.getByText("/Users/michael/Projects/23-chatReviewer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open evidence/i })).toHaveAttribute("href", "/trace/41");

    fireEvent.click(screen.getByRole("button", { name: /done 1/i }));
    expect(screen.getByText("Completed evidence migration")).toBeInTheDocument();
    expect(screen.queryByText("Finish the active archive synchronization")).not.toBeInTheDocument();
  });

  it("keeps cross-chat assessments out of the summary dashboard", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => response,
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<MemoryRouter><DashboardPage /></MemoryRouter>);

    expect(await screen.findByText("Finish the active archive synchronization")).toBeInTheDocument();
    expect(screen.queryByText("Next Up")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/resume-surfaces?limit=200", expect.anything());
  });
});
