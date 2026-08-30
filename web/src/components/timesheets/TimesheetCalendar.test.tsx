import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  RepositoryEvidenceSymbols,
  TimesheetCalendar,
  activityLevel,
  buildCalendarWeeks,
  dayEvidenceKinds,
  daySourceClass,
  evidenceActivityLevel,
  financialYearDates,
  financialYearForDate,
  prioritizeActiveProjects,
  updateProjectSelection,
} from "./TimesheetCalendar";

afterEach(() => vi.unstubAllGlobals());

describe("TimesheetCalendar helpers", () => {
  it("builds a complete Sunday-to-Saturday calendar grid", () => {
    const weeks = buildCalendarWeeks("2025-07-01", "2026-06-30");
    const dates = weeks.flatMap((week) => week.dates).filter(Boolean);

    expect(weeks).toHaveLength(53);
    expect(dates[0]).toBe("2025-07-01");
    expect(dates.at(-1)).toBe("2026-06-30");
    expect(dates).toHaveLength(365);
    expect(weeks[0].dates.slice(0, 2)).toEqual([null, null]);
  });

  it("maps dates and labels onto Australian financial years", () => {
    expect(financialYearForDate("2026-06-30")).toBe("2025-26");
    expect(financialYearForDate("2026-07-01")).toBe("2026-27");
    expect(financialYearDates("2025-26")).toEqual(["2025-07-01", "2026-06-30"]);
  });

  it("uses stable, interpretable daily time bands", () => {
    expect(activityLevel(0)).toBe(0);
    expect(activityLevel(15 * 60)).toBe(1);
    expect(activityLevel(60 * 60)).toBe(2);
    expect(activityLevel(3 * 60 * 60)).toBe(3);
    expect(activityLevel(3 * 60 * 60 + 1)).toBe(4);
  });

  it("makes an evidence-only work day visible", () => {
    expect(evidenceActivityLevel(0, 0)).toBe(0);
    expect(evidenceActivityLevel(0, 1)).toBe(1);
    expect(evidenceActivityLevel(60 * 60, 1)).toBe(2);
  });

  it("moves repositories active on the selected day to the top", () => {
    const projects = [
      { project_key: "annual-leader" },
      { project_key: "short-session" },
      { project_key: "long-session" },
      { project_key: "inactive" },
    ];

    expect(prioritizeActiveProjects(projects, [
      { project_key: "short-session", exact_seconds: 600 },
      { project_key: "long-session", exact_seconds: 3600 },
    ])).toEqual([
      { project_key: "long-session" },
      { project_key: "short-session" },
      { project_key: "annual-leader" },
      { project_key: "inactive" },
    ]);
    expect(projects.map((project) => project.project_key)).toEqual([
      "annual-leader",
      "short-session",
      "long-session",
      "inactive",
    ]);
  });

  it("pins selected repositories ahead of day matches in selection order", () => {
    const projects = [
      { project_key: "annual-leader" },
      { project_key: "selected-second" },
      { project_key: "day-match" },
      { project_key: "selected-first" },
    ];

    expect(prioritizeActiveProjects(
      projects,
      [{ project_key: "day-match", exact_seconds: 3600 }],
      ["selected-first", "selected-second"],
    ).map((project) => project.project_key)).toEqual([
      "selected-first",
      "selected-second",
      "day-match",
      "annual-leader",
    ]);
  });

  it("uses Shift-click to add or remove repositories", () => {
    expect(updateProjectSelection([], "repo-a", false)).toEqual(["repo-a"]);
    expect(updateProjectSelection(["repo-a"], "repo-b", true)).toEqual(["repo-a", "repo-b"]);
    expect(updateProjectSelection(["repo-a", "repo-b"], "repo-a", true)).toEqual(["repo-b"]);
    expect(updateProjectSelection(["repo-a", "repo-b"], "repo-b", false)).toEqual(["repo-b"]);
    expect(updateProjectSelection(["repo-b"], "repo-b", false)).toEqual([]);
  });

  it("shows mixed Git, AI chat, and source-device symbols", () => {
    const machines = [
      { machine_id: "machine-a", machine_name: "workstation-alpha" },
      { machine_id: "laptop", machine_name: "Studio laptop" },
    ];
    render(
      <RepositoryEvidenceSymbols
        evidenceKinds={["git", "chat"]}
        machines={machines}
        providers={["codex", "gemini", "git"]}
      />,
    );

    expect(screen.getByLabelText("Git commits and local Git operations")).toBeInTheDocument();
    expect(screen.getByLabelText("AI chat activity: Codex, Gemini")).toBeInTheDocument();
    expect(screen.getByLabelText("Source device: workstation-alpha")).toBeInTheDocument();
    expect(screen.getByLabelText("Source device: Studio laptop")).toBeInTheDocument();
  });

  it("computes a timestamp union only after the repository selection is applied", async () => {
    const projects = [
      {
        project_id: 1,
        project_key: "repo-a-key",
        project: "Repo A",
        exact_seconds: 7_200,
        interval_count: 1,
        evidence_count: 2,
        ambiguous_seconds: 0,
        active_days: 1,
        first_date: "2026-07-18",
        last_date: "2026-07-18",
        providers: ["codex"],
        evidence_kinds: ["chat"],
        machines: [],
      },
      {
        project_id: 2,
        project_key: "repo-b-key",
        project: "Repo B",
        exact_seconds: 7_200,
        interval_count: 1,
        evidence_count: 2,
        ambiguous_seconds: 0,
        active_days: 1,
        first_date: "2026-07-18",
        last_date: "2026-07-18",
        providers: ["claude"],
        evidence_kinds: ["chat"],
        machines: [],
      },
    ];
    const calendar = {
      financial_year: "2026-27",
      available_financial_years: ["2026-27"],
      date_from: "2026-07-01",
      date_to: "2027-06-30",
      days: [{
        date: "2026-07-18",
        exact_seconds: 14_400,
        interval_count: 2,
        evidence_count: 4,
        ambiguous_seconds: 0,
        projects,
      }],
      projects,
    };
    const combined = {
      calculation_key: "combined-key",
      financial_year: "2026-27",
      date_from: "2026-07-01",
      date_to: "2027-06-30",
      projects: projects.map(({ project_key, project }) => ({ project_key, project })),
      project_keys: ["repo-a-key", "repo-b-key"],
      exact_seconds: 10_800,
      raw_seconds: 14_400,
      overlap_seconds: 3_600,
      multi_project_seconds: 3_600,
      active_days: 1,
      interval_count: 3,
      evidence_count: 4,
      days: [{
        date: "2026-07-18",
        exact_seconds: 10_800,
        raw_seconds: 14_400,
        overlap_seconds: 3_600,
        evidence_count: 4,
        contributor_count: 1,
      }],
      contributor_days: [],
      contributors: [],
      intervals: [],
    };
    let computeInit: RequestInit | undefined;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = input instanceof Request ? input.url : String(input);
      if (path.includes("/api/timesheets/compute")) computeInit = init;
      const payload = path.includes("/api/timesheets/calendar")
        ? calendar
        : path.includes("/api/timesheets/compute")
          ? combined
          : { rows: [] };
      return new Response(JSON.stringify(payload), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<TimesheetCalendar financialYear="2026-27" setFinancialYear={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Repo A/ }));
    fireEvent.click(screen.getByRole("button", { name: /Repo B/ }), { shiftKey: true });

    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/timesheets/compute",
      expect.anything(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Compute 2 repositories" }));

    await waitFor(() => {
      expect(screen.getByText("combined human hours").parentElement).toHaveTextContent("3.0h");
    });
    expect(screen.getByText("overlap removed").parentElement).toHaveTextContent("1.0h");
    const computeRequest = fetchMock.mock.calls.find(
      ([input]) => String(input).includes("/api/timesheets/compute"),
    );
    expect(computeRequest).toBeDefined();
    expect(JSON.parse(String(computeInit?.body))).toEqual({
      financial_year: "2026-27",
      project_keys: ["repo-a-key", "repo-b-key"],
    });

    fireEvent.click(screen.getByRole("button", { name: /Repo A/ }));
    expect(screen.getByText("Selection changed — recompute required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recompute 1 repository" })).toBeInTheDocument();
    expect(screen.getByText("independent activity hours").parentElement).toHaveTextContent("2.0h");
  });

  it("keeps Git and chat evidence distinct at day level", () => {
    const day = {
      evidence_kinds: ["git"] as Array<"git" | "chat">,
      projects: [
        { project_key: "git-only", evidence_kinds: ["git"] as Array<"git" | "chat"> },
        { project_key: "chat-only", evidence_kinds: ["chat"] as Array<"git" | "chat"> },
      ],
    };

    expect(daySourceClass(dayEvidenceKinds(day, ["git-only"]))).toBe("source-git");
    expect(daySourceClass(dayEvidenceKinds(day, ["chat-only"]))).toBe("source-chat");
    expect(daySourceClass(dayEvidenceKinds(day, []))).toBe("source-both");
    expect(daySourceClass(dayEvidenceKinds(day, ["missing"]))).toBe("source-none");
  });

  it("gives each month label the width of its calendar segment", async () => {
    const calendar = {
      financial_year: "2025-26",
      available_financial_years: ["2025-26"],
      date_from: "2025-07-01",
      date_to: "2026-06-30",
      days: [],
      projects: [],
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const payload = String(input).includes("/api/timesheets/calendar") ? calendar : { rows: [] };
      return new Response(JSON.stringify(payload), {
        headers: { "Content-Type": "application/json" },
        status: 200,
      });
    }));

    const { container } = render(
      <TimesheetCalendar financialYear="2025-26" setFinancialYear={vi.fn()} />,
    );
    await screen.findByText("0 work days in FY 2025-26");
    const monthLabels = container.querySelectorAll(".timesheet-calendar-chart .timesheet-month-labels span");

    expect(monthLabels).toHaveLength(12);
    expect([...monthLabels].map((label) => {
      const style = (label as HTMLElement).style;
      return [style.gridColumnStart, style.gridColumnEnd];
    })).toEqual([
      ["1", "5"],
      ["5", "10"],
      ["10", "14"],
      ["14", "18"],
      ["18", "23"],
      ["23", "27"],
      ["27", "32"],
      ["32", "36"],
      ["36", "40"],
      ["40", "44"],
      ["44", "49"],
      ["49", "54"],
    ]);
  });
});
