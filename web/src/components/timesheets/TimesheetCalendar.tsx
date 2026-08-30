import {
  BarChart3,
  CalendarDays,
  Clock3,
  FolderGit2,
  GitCommitHorizontal,
  GitMerge,
  MessageSquareText,
  Monitor,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api, queryString, useApi } from "../../api";
import {
  Badge,
  ErrorNotice,
  Loading,
  formatDate,
  formatDuration,
  formatHours,
  formatNumber,
} from "../Common";

export interface TimesheetIntervalRow {
  id: number;
  local_date: string;
  started_at?: string;
  ended_at?: string;
  exact_seconds: number;
  ambiguous: boolean;
  ambiguity_reason?: string | null;
  evidence_count: number;
  contributor: string | null;
  project: string | null;
  activity: string | null;
  classification: string;
}

interface CalendarProjectSlice {
  project_id: number | null;
  project_key: string;
  project: string;
  exact_seconds: number;
  interval_count: number;
  evidence_count: number;
  ambiguous_seconds: number;
  evidence_kinds?: Array<"git" | "chat">;
}

interface CalendarDay {
  date: string;
  exact_seconds: number;
  interval_count: number;
  evidence_count: number;
  ambiguous_seconds: number;
  evidence_kinds?: Array<"git" | "chat">;
  projects: CalendarProjectSlice[];
}

interface CalendarProject extends CalendarProjectSlice {
  active_days: number;
  first_date: string;
  last_date: string;
  providers: string[];
  evidence_kinds: Array<"git" | "chat">;
  machines: CalendarMachine[];
}

export interface CalendarMachine {
  machine_id: string;
  machine_name: string;
}

interface CalendarResponse {
  financial_year: string;
  available_financial_years: string[];
  date_from: string;
  date_to: string;
  days: CalendarDay[];
  projects: CalendarProject[];
}

interface IntervalResponse {
  rows: TimesheetIntervalRow[];
}

interface CombinedTimesheetDay {
  date: string;
  exact_seconds: number;
  raw_seconds: number;
  overlap_seconds: number;
  evidence_count: number;
  contributor_count: number;
}

interface CombinedTimesheetInterval {
  date: string;
  started_at: string;
  ended_at: string;
  exact_seconds: number;
  contributor_id: number | null;
  contributor: string;
  projects: Array<{ project_key: string; project: string }>;
  ambiguous: boolean;
  source_interval_ids: number[];
}

interface CombinedTimesheetResponse {
  calculation_key: string;
  financial_year: string;
  project_keys: string[];
  exact_seconds: number;
  raw_seconds: number;
  overlap_seconds: number;
  multi_project_seconds: number;
  active_days: number;
  interval_count: number;
  evidence_count: number;
  days: CombinedTimesheetDay[];
  intervals: CombinedTimesheetInterval[];
}

interface AppliedCombinedTimesheet {
  financialYear: string;
  requestedProjectKeys: string[];
  result: CombinedTimesheetResponse;
}

interface CalendarWeek {
  dates: Array<string | null>;
}

type EvidenceKind = "git" | "chat";

const DAY_LABELS = ["", "Mon", "", "Wed", "", "Fri", ""];
export function TimesheetCalendar({
  financialYear,
  setFinancialYear,
}: {
  financialYear: string;
  setFinancialYear: (value: string) => void;
}) {
  const [projectKeys, setProjectKeys] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [combined, setCombined] = useState<AppliedCombinedTimesheet | null>(null);
  const [computeLoading, setComputeLoading] = useState(false);
  const [computeError, setComputeError] = useState<string | null>(null);
  const calendar = useApi<CalendarResponse>(
    `/api/timesheets/calendar?${queryString({ financial_year: financialYear })}`,
  );
  const selectedProjects = useMemo(
    () => (calendar.data?.projects ?? []).filter((project) => projectKeys.includes(project.project_key)),
    [calendar.data?.projects, projectKeys],
  );
  const effectiveProjectKeys = useMemo(
    () => selectedProjects.map((project) => project.project_key),
    [selectedProjects],
  );
  const detailPath = selectedDate || calendar.data
    ? `/api/timesheets?${queryString({
        date_from: selectedDate ?? calendar.data?.date_from,
        date_to: selectedDate ?? calendar.data?.date_to,
        projects: effectiveProjectKeys,
        limit: selectedDate ? 2000 : 20,
      })}`
    : null;
  const details = useApi<IntervalResponse>(detailPath);

  const weeks = useMemo(
    () => buildCalendarWeeks(...financialYearDates(financialYear)),
    [financialYear],
  );
  const dayMap = useMemo(
    () => new Map((calendar.data?.days ?? []).map((day) => [day.date, day])),
    [calendar.data?.days],
  );
  const combinedIsCurrent = combined !== null
    && combined.financialYear === financialYear
    && sameProjectSelection(combined.requestedProjectKeys, effectiveProjectKeys);
  const combinedNeedsRecompute = combined !== null && !combinedIsCurrent;
  const combinedDayMap = useMemo(
    () => new Map(
      (combinedIsCurrent ? combined.result.days : []).map((day) => [day.date, day]),
    ),
    [combined, combinedIsCurrent],
  );
  const selectedDays = useMemo(
    () => (calendar.data?.days ?? []).map((day) => ({
      day,
      evidence: combinedDayMap.get(day.date)?.evidence_count
        ?? dayEvidence(day, effectiveProjectKeys),
      seconds: combinedDayMap.get(day.date)?.exact_seconds
        ?? daySeconds(day, effectiveProjectKeys),
    })),
    [calendar.data?.days, combinedDayMap, effectiveProjectKeys],
  );
  const duplicateProjectNames = useMemo(() => {
    const counts = new Map<string, number>();
    (calendar.data?.projects ?? []).forEach((project) => {
      counts.set(project.project, (counts.get(project.project) ?? 0) + 1);
    });
    return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name));
  }, [calendar.data?.projects]);
  const selectedSeconds = combinedIsCurrent
    ? combined.result.exact_seconds
    : selectedDays.reduce((total, item) => total + item.seconds, 0);
  const activeDays = combinedIsCurrent
    ? combined.result.active_days
    : selectedDays.filter((item) => item.seconds > 0 || item.evidence > 0).length;
  const selectedEvidence = combinedIsCurrent
    ? combined.result.evidence_count
    : selectedDays.reduce((total, item) => total + item.evidence, 0);
  const rows = details.data?.rows ?? [];
  const selectedDay = selectedDate ? dayMap.get(selectedDate) : null;
  const selectedCombinedDay = selectedDate ? combinedDayMap.get(selectedDate) : null;
  const selectedCombinedIntervals = combinedIsCurrent && selectedDate
    ? combined.result.intervals.filter((interval) => interval.date === selectedDate)
    : [];

  async function computeSelection() {
    setComputeLoading(true);
    setComputeError(null);
    const requestedProjectKeys = [...effectiveProjectKeys];
    try {
      const result = await api<CombinedTimesheetResponse>("/api/timesheets/compute", {
        body: JSON.stringify({
          financial_year: financialYear,
          project_keys: requestedProjectKeys,
        }),
        method: "POST",
      });
      setCombined({ financialYear, requestedProjectKeys, result });
    } catch (reason) {
      setComputeError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setComputeLoading(false);
    }
  }

  if (calendar.loading) return <Loading label="Building the daily work calendar" />;
  if (calendar.error) return <ErrorNotice message={calendar.error} />;
  if (!calendar.data) return null;

  return (
    <>
      <section className="panel timesheet-calendar-panel">
        <div className="timesheet-section-heading">
          <div>
            <span className="eyebrow">Daily evidence</span>
            <h2>{formatNumber(activeDays)} work days in FY {financialYear}</h2>
            <p>
              {combinedIsCurrent
                ? "Each square is deduplicated human time. Select a day to inspect its merged intervals."
                : "Green marks Git activity; orange marks archived AI conversation activity. A full green square means Git evidence exists but no AI conversation evidence is currently archived for that day. Repository clocks are independent and non-additive until Compute is pressed."}
            </p>
          </div>
          <div className="timesheet-calendar-filters">
            <label>
              <span>Repositories</span>
              <select
                value={effectiveProjectKeys.length > 1 ? "__multiple__" : effectiveProjectKeys[0] ?? "__all__"}
                onChange={(event) => {
                  setProjectKeys(event.target.value === "__all__" ? [] : [event.target.value]);
                  setSelectedDate(null);
                }}
              >
                <option value="__all__">All repositories</option>
                {effectiveProjectKeys.length > 1 ? (
                  <option value="__multiple__" disabled>{effectiveProjectKeys.length} repositories selected</option>
                ) : null}
                {calendar.data.projects.map((project) => (
                  <option key={project.project_key} value={project.project_key}>
                    {projectLabel(project, duplicateProjectNames)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Financial year</span>
              <select value={financialYear} onChange={(event) => { setFinancialYear(event.target.value); setProjectKeys([]); setSelectedDate(null); setCombined(null); }}>
                {financialYearOptions(calendar.data.available_financial_years, financialYear).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        <div className="timesheet-focus-stats">
          <div><Clock3 /><strong>{formatHours(selectedSeconds)}</strong><span>{combinedIsCurrent ? "combined human hours" : "independent activity hours"}</span></div>
          <div><CalendarDays /><strong>{formatNumber(activeDays)}</strong><span>active days</span></div>
          <div><FolderGit2 /><strong>{formatNumber(effectiveProjectKeys.length || calendar.data.projects.length)}</strong><span>{effectiveProjectKeys.length ? "selected repositories" : "repositories"}</span></div>
          <div><GitMerge /><strong>{combinedIsCurrent ? formatHours(combined.result.overlap_seconds) : "—"}</strong><span>{combinedIsCurrent ? "overlap removed" : "press Compute"}</span></div>
          <div><BarChart3 /><strong>{formatNumber(selectedEvidence)}</strong><span>evidence events</span></div>
        </div>

        <div className="timesheet-calendar-scroll">
          <div className="timesheet-calendar-chart">
            <MonthHeader weeks={weeks} dateFrom={calendar.data.date_from} />
            <div className="timesheet-calendar-body">
              <div className="timesheet-weekday-labels">
                {DAY_LABELS.map((label, index) => <span key={index}>{label}</span>)}
              </div>
              <div className="timesheet-calendar-weeks">
                {weeks.map((week, weekIndex) => (
                  <div className="timesheet-calendar-week" key={weekIndex}>
                    {week.dates.map((date, dayIndex) => {
                      if (!date) return <span className="timesheet-day-empty" key={dayIndex} />;
                      const day = dayMap.get(date);
                      const combinedDay = combinedDayMap.get(date);
                      const seconds = combinedDay?.exact_seconds
                        ?? (day ? daySeconds(day, effectiveProjectKeys) : 0);
                      const evidence = combinedDay?.evidence_count
                        ?? (day ? dayEvidence(day, effectiveProjectKeys) : 0);
                      const evidenceKinds = dayEvidenceKinds(day, effectiveProjectKeys);
                      return (
                        <button
                          aria-label={dayLabel(date, seconds, day, effectiveProjectKeys)}
                          aria-pressed={selectedDate === date}
                          className={`timesheet-day level-${evidenceActivityLevel(seconds, evidence)} ${daySourceClass(evidenceKinds)} ${selectedDate === date ? "selected" : ""}`}
                          key={date}
                          onClick={() => setSelectedDate((current) => current === date ? null : date)}
                          title={dayLabel(date, seconds, day, effectiveProjectKeys)}
                          type="button"
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="timesheet-calendar-footer">
          <span>
            {combinedIsCurrent
              ? `${selectedProjectSummary(selectedProjects)} · timestamp overlaps removed`
              : `${selectedProjectSummary(selectedProjects)} · independent clocks, not additive`}
          </span>
          <div className="timesheet-source-legend" aria-label="Calendar evidence source legend">
            <span><i className="source-git" />Git activity</span>
            <span><i className="source-chat" />AI conversation</span>
            <span><i className="source-both" />Both sources</span>
          </div>
        </div>
      </section>

      <RepositoryTimeline
        calendar={calendar.data}
        projectKeys={effectiveProjectKeys}
        setProjectKeys={setProjectKeys}
        combinedIsCurrent={combinedIsCurrent}
        combinedNeedsRecompute={combinedNeedsRecompute}
        computeError={computeError}
        computeLoading={computeLoading}
        onCompute={() => void computeSelection()}
        selectedDate={selectedDate}
        weeks={weeks}
        dateFrom={calendar.data.date_from}
        financialYear={financialYear}
      />

      <section className="panel archive-panel archive-table-wrap timesheet-detail-panel">
        <div className="timesheet-section-heading compact">
          <div>
            <span className="eyebrow">Interval evidence</span>
            <h2>{selectedDate ? formatDate(selectedDate) : `FY ${financialYear} interval sample`}</h2>
            <p>
              {selectedDate
                ? combinedIsCurrent
                  ? `${formatHours(selectedCombinedDay?.exact_seconds ?? 0)} combined human time across ${formatNumber(selectedCombinedIntervals.length)} merged intervals; ${formatNumber(rows.length)} source records are non-additive evidence.`
                  : `${formatHours(daySeconds(selectedDay, effectiveProjectKeys))} across ${formatNumber(rows.length)} independent interval records; press Compute before treating them as human hours.`
                : "Showing 20 interval records. Select a calendar square to inspect every interval recorded for that day."}
            </p>
          </div>
          {selectedDate ? <button className="button" type="button" onClick={() => setSelectedDate(null)}>Clear day</button> : null}
        </div>
        {details.loading ? <Loading label="Reading interval evidence" /> : null}
        {details.error ? <ErrorNotice message={details.error} /> : null}
        {!details.loading && !details.error && combinedIsCurrent && selectedDate ? (
          <table className="archive-table combined-timesheet-table">
            <thead><tr><th>Date / span</th><th>Contributor</th><th>Repositories</th><th>Time</th><th>Source clocks</th></tr></thead>
            <tbody>
              {selectedCombinedIntervals.map((interval) => (
                <tr key={`${interval.contributor_id}-${interval.started_at}-${interval.ended_at}`}>
                  <td>{formatDate(interval.date)}<small>{combinedIntervalSpan(interval)}</small></td>
                  <td>{interval.contributor}</td>
                  <td>
                    {interval.projects.map((project) => project.project).join(", ")}
                    {interval.projects.length > 1 ? <Badge tone="partial">multi-project</Badge> : null}
                  </td>
                  <td>{formatDuration(interval.exact_seconds)}{interval.ambiguous ? <Badge tone="partial">ambiguous</Badge> : null}</td>
                  <td>{formatNumber(interval.source_interval_ids.length)} intervals</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
        {!details.loading && !details.error && (!combinedIsCurrent || !selectedDate) ? (
          <table className="archive-table">
            <thead><tr><th>Date / span</th><th>Contributor</th><th>Repository</th><th>Activity</th><th>Time</th><th>Evidence</th></tr></thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatDate(row.local_date)}<small>{intervalSpan(row)}</small></td>
                  <td>{row.contributor ?? "Unresolved"}</td>
                  <td>{row.project ?? "Unallocated"}</td>
                  <td>{row.activity ?? "Unclassified"}<small>{row.classification}</small></td>
                  <td>{formatDuration(row.exact_seconds)}{row.ambiguous ? <Badge tone="partial">ambiguous</Badge> : null}</td>
                  <td>{formatNumber(row.evidence_count)} events</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>
    </>
  );
}

function RepositoryTimeline({
  calendar,
  projectKeys,
  setProjectKeys,
  combinedIsCurrent,
  combinedNeedsRecompute,
  computeError,
  computeLoading,
  onCompute,
  selectedDate,
  weeks,
  dateFrom,
  financialYear,
}: {
  calendar: CalendarResponse;
  projectKeys: string[];
  setProjectKeys: (value: string[]) => void;
  combinedIsCurrent: boolean;
  combinedNeedsRecompute: boolean;
  computeError: string | null;
  computeLoading: boolean;
  onCompute: () => void;
  selectedDate: string | null;
  weeks: CalendarWeek[];
  dateFrom: string;
  financialYear: string;
}) {
  const duplicateProjectNames = useMemo(() => {
    const counts = new Map<string, number>();
    calendar.projects.forEach((project) => {
      counts.set(project.project, (counts.get(project.project) ?? 0) + 1);
    });
    return new Set([...counts].filter(([, count]) => count > 1).map(([name]) => name));
  }, [calendar.projects]);
  const weeklyTotals = useMemo(() => {
    const dateToWeek = new Map<string, number>();
    weeks.forEach((week, weekIndex) => {
      week.dates.forEach((date) => {
        if (date) dateToWeek.set(date, weekIndex);
      });
    });
    const totals = new Map<string, Array<{ evidence: number; seconds: number }>>();
    calendar.days.forEach((day) => {
      const weekIndex = dateToWeek.get(day.date);
      if (weekIndex === undefined) return;
      day.projects.forEach((project) => {
        const projectTotals = totals.get(project.project_key)
          ?? Array.from({ length: weeks.length }, () => ({ evidence: 0, seconds: 0 }));
        projectTotals[weekIndex].seconds += project.exact_seconds;
        projectTotals[weekIndex].evidence += project.evidence_count;
        totals.set(project.project_key, projectTotals);
      });
    });
    return totals;
  }, [calendar.days, weeks]);
  const selectedDay = selectedDate
    ? calendar.days.find((day) => day.date === selectedDate)
    : undefined;
  const selectedProjectMap = new Map(
    (selectedDay?.projects ?? []).map((project) => [project.project_key, project]),
  );
  const orderedProjects = prioritizeActiveProjects(
    calendar.projects,
    selectedDay?.projects,
    projectKeys,
  );
  return (
    <section className="panel repository-timeline-panel">
      <div className="timesheet-section-heading compact">
        <div>
          <span className="eyebrow">Repository timeline</span>
          <h2>When each repository was active</h2>
          <p>
            {selectedDate
              ? `Selected repositories stay pinned first; repositories active on ${formatDate(selectedDate)} follow. Row hours are independent and non-additive.`
              : "Click to focus; Shift-click to build a selection. Row hours are independent and non-additive until Compute is pressed."}
          </p>
          <div className="repository-evidence-legend" aria-label="Repository evidence symbol legend">
            <span><GitCommitHorizontal aria-hidden="true" />Git commits / operations</span>
            <span><MessageSquareText aria-hidden="true" />AI chat activity</span>
            <span><Monitor aria-hidden="true" />Source device</span>
          </div>
        </div>
        <div className="repository-timeline-actions">
          {combinedNeedsRecompute ? (
            <span className="timesheet-recompute-notice">Selection changed — recompute required</span>
          ) : null}
          <button
            className="button button-primary"
            disabled={computeLoading}
            onClick={onCompute}
            type="button"
          >
            {computeLoading
              ? "Computing…"
              : `${combinedIsCurrent || combinedNeedsRecompute ? "Recompute" : "Compute"} ${projectKeys.length || "all"} ${projectKeys.length === 1 ? "repository" : "repositories"}`}
          </button>
          {projectKeys.length ? <button className="button" type="button" onClick={() => setProjectKeys([])}>Show all</button> : null}
        </div>
      </div>
      {computeError ? <ErrorNotice message={computeError} /> : null}
      <div className="repository-timeline-scroll">
        <div className="repository-timeline">
          <div className="repository-timeline-months"><span /><MonthHeader weeks={weeks} dateFrom={dateFrom} /></div>
          {orderedProjects.slice(0, 20).map((project) => {
            const selectedDayProject = selectedProjectMap.get(project.project_key);
            return (
              <button
                aria-pressed={projectKeys.includes(project.project_key)}
                className={`repository-timeline-row ${projectKeys.includes(project.project_key) ? "active" : ""} ${selectedDayProject ? "day-match" : ""}`}
                key={project.project_key}
                onClick={(event) => setProjectKeys(updateProjectSelection(
                  projectKeys,
                  project.project_key,
                  event.shiftKey,
                ))}
                title="Click to focus this repository; Shift-click to add or remove it"
                type="button"
              >
                <span className="repository-timeline-label">
                  <strong>{projectLabel(project, duplicateProjectNames)}</strong>
                  <small>
                    {selectedDayProject
                      ? `${formatHours(selectedDayProject.exact_seconds)} independent activity on selected day · ${formatHours(project.exact_seconds)} FY activity`
                      : `${formatHours(project.exact_seconds)} independent activity · ${formatNumber(project.active_days)} days`}
                  </small>
                  <RepositoryEvidenceSymbols
                    evidenceKinds={project.evidence_kinds}
                    machines={project.machines}
                    providers={project.providers}
                  />
                </span>
                <span className="repository-timeline-weeks">
                  {weeks.map((_, index) => {
                    const total = weeklyTotals.get(project.project_key)?.[index] ?? { evidence: 0, seconds: 0 };
                    return <i className={`level-${weeklyActivityLevel(total.seconds, total.evidence)}`} key={index} title={`${formatDuration(total.seconds)} · ${formatNumber(total.evidence)} evidence events in week ${index + 1}`} />;
                  })}
                </span>
              </button>
            );
          })}
        </div>
      </div>
      {calendar.projects.length > 20 ? (
        <p className="archive-caveat">
          {projectKeys.length
            ? `Selected repositories are pinned first${selectedDate ? `, followed by repositories active on ${formatDate(selectedDate)}` : ""}, then the highest calculated time in FY ${financialYear}; limited to 20 rows.`
            : selectedDate
              ? `Showing repositories active on ${formatDate(selectedDate)} first, then the highest calculated time in FY ${financialYear}; limited to 20 rows.`
              : `Showing the 20 repositories with the most calculated time in FY ${financialYear}.`}
        </p>
      ) : null}
    </section>
  );
}

export function RepositoryEvidenceSymbols({
  evidenceKinds,
  machines,
  providers,
}: {
  evidenceKinds: Array<"git" | "chat">;
  machines: CalendarMachine[];
  providers: string[];
}) {
  const chatProviders = providers.filter((provider) => provider !== "git");
  return (
    <span className="repository-evidence-symbols">
      {evidenceKinds.includes("git") ? (
        <span
          aria-label="Git commits and local Git operations"
          className="repository-evidence-symbol repository-evidence-git"
          role="img"
          title="Git commits, stashes, and attributed local Git operations"
        >
          <GitCommitHorizontal aria-hidden="true" />Git
        </span>
      ) : null}
      {evidenceKinds.includes("chat") ? (
        <span
          aria-label={`AI chat activity: ${chatProviders.map(providerName).join(", ")}`}
          className="repository-evidence-symbol repository-evidence-chat"
          role="img"
          title={`AI chat activity: ${chatProviders.map(providerName).join(", ")}`}
        >
          <MessageSquareText aria-hidden="true" />AI
        </span>
      ) : null}
      {machines.map((machine) => (
        <span
          aria-label={`Source device: ${machine.machine_name}`}
          className="repository-evidence-symbol repository-evidence-device"
          key={machine.machine_id}
          role="img"
          title={`Source device: ${machine.machine_name}`}
        >
          <Monitor aria-hidden="true" />{machine.machine_name}
        </span>
      ))}
    </span>
  );
}

function providerName(provider: string): string {
  return provider === "codex"
    ? "Codex"
    : provider === "claude"
      ? "Claude"
      : provider === "gemini"
        ? "Gemini"
        : provider;
}

function MonthHeader({ weeks, dateFrom }: { weeks: CalendarWeek[]; dateFrom: string }) {
  return (
    <div className="timesheet-month-labels" style={{ gridTemplateColumns: `repeat(${weeks.length}, var(--calendar-day))` }}>
      {financialYearMonths(dateFrom).map((month) => (
        <span style={{ gridColumnStart: monthWeekIndex(dateFrom, month.date) + 1 }} key={month.date}>{month.label}</span>
      ))}
    </div>
  );
}

export function buildCalendarWeeks(dateFrom: string, dateTo: string): CalendarWeek[] {
  const periodStart = utcDate(dateFrom);
  const periodEnd = utcDate(dateTo);
  const first = new Date(periodStart);
  first.setUTCDate(first.getUTCDate() - first.getUTCDay());
  const last = new Date(periodEnd);
  last.setUTCDate(last.getUTCDate() + (6 - last.getUTCDay()));
  const weeks: CalendarWeek[] = [];
  const cursor = new Date(first);
  while (cursor <= last) {
    const dates: Array<string | null> = [];
    for (let day = 0; day < 7; day += 1) {
      dates.push(cursor >= periodStart && cursor <= periodEnd ? isoDate(cursor) : null);
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    weeks.push({ dates });
  }
  return weeks;
}

export function activityLevel(seconds: number): number {
  if (seconds <= 0) return 0;
  if (seconds <= 15 * 60) return 1;
  if (seconds <= 60 * 60) return 2;
  if (seconds <= 3 * 60 * 60) return 3;
  return 4;
}

export function evidenceActivityLevel(seconds: number, evidence: number): number {
  if (seconds <= 0 && evidence > 0) return 1;
  return activityLevel(seconds);
}

export function dayEvidenceKinds(
  day: {
    evidence_kinds?: EvidenceKind[];
    projects: Array<Pick<CalendarProjectSlice, "project_key" | "evidence_kinds">>;
  } | null | undefined,
  projectKeys: string[],
): EvidenceKind[] {
  if (!day) return [];
  const projects = projectKeys.length
    ? day.projects.filter((project) => projectKeys.includes(project.project_key))
    : day.projects;
  const kinds = new Set<EvidenceKind>(!projectKeys.length ? day.evidence_kinds ?? [] : []);
  projects.forEach((project) => {
    project.evidence_kinds?.forEach((kind) => kinds.add(kind));
  });
  const orderedKinds: EvidenceKind[] = ["git", "chat"];
  return orderedKinds.filter((kind) => kinds.has(kind));
}

export function daySourceClass(kinds: EvidenceKind[]): string {
  if (kinds.length === 2) return "source-both";
  if (kinds[0] === "git") return "source-git";
  if (kinds[0] === "chat") return "source-chat";
  return "source-none";
}

function weeklyActivityLevel(seconds: number, evidence: number): number {
  if (seconds <= 0) return evidence > 0 ? 1 : 0;
  if (seconds <= 60 * 60) return 1;
  if (seconds <= 4 * 60 * 60) return 2;
  if (seconds <= 12 * 60 * 60) return 3;
  return 4;
}

function daySeconds(day: CalendarDay | null | undefined, projectKeys: string[]): number {
  if (!day) return 0;
  if (!projectKeys.length) return day.exact_seconds;
  const selected = new Set(projectKeys);
  return day.projects.reduce(
    (total, project) => total + (selected.has(project.project_key) ? project.exact_seconds : 0),
    0,
  );
}

function dayEvidence(day: CalendarDay | null | undefined, projectKeys: string[]): number {
  if (!day) return 0;
  if (!projectKeys.length) return day.evidence_count;
  const selected = new Set(projectKeys);
  return day.projects.reduce(
    (total, project) => total + (selected.has(project.project_key) ? project.evidence_count : 0),
    0,
  );
}

function dayLabel(date: string, seconds: number, day: CalendarDay | undefined, projectKeys: string[]): string {
  const project = projectKeys.length === 1
    ? day?.projects.find((item) => item.project_key === projectKeys[0])
    : null;
  const suffix = project
    ? ` on ${project.project}`
    : projectKeys.length > 1
      ? ` across ${projectKeys.length} selected repositories`
      : day?.projects.length
        ? ` across ${day.projects.length} repositories`
        : "";
  const evidence = dayEvidence(day, projectKeys);
  const kinds = dayEvidenceKinds(day, projectKeys);
  const sources = kinds.length
    ? `, ${kinds.map((kind) => kind === "git" ? "Git activity" : "AI conversation").join(" + ")}`
    : "";
  return `${formatDate(date)}: ${formatDuration(seconds)}, ${formatNumber(evidence)} evidence events${sources}${suffix}`;
}

function selectedProjectSummary(projects: CalendarProject[]): string {
  if (!projects.length) return "All repository work";
  if (projects.length === 1) return projects[0].project;
  return `${formatNumber(projects.length)} selected repositories`;
}

function projectLabel(project: CalendarProject, duplicateNames: Set<string>): string {
  return duplicateNames.has(project.project)
    ? `${project.project} · ${project.project_key.slice(-8)}`
    : project.project;
}

function intervalSpan(row: TimesheetIntervalRow): string {
  if (!row.started_at || !row.ended_at) return row.ambiguous ? row.ambiguity_reason ?? "Ambiguous" : "Calculated interval";
  const formatter = new Intl.DateTimeFormat("en-AU", { hour: "2-digit", minute: "2-digit" });
  return `${formatter.format(new Date(row.started_at))}–${formatter.format(new Date(row.ended_at))}`;
}

function combinedIntervalSpan(interval: CombinedTimesheetInterval): string {
  const formatter = new Intl.DateTimeFormat("en-AU", { hour: "2-digit", minute: "2-digit" });
  return `${formatter.format(new Date(interval.started_at))}–${formatter.format(new Date(interval.ended_at))}`;
}

function sameProjectSelection(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  const selected = new Set(left);
  return right.every((projectKey) => selected.has(projectKey));
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function monthWeekIndex(dateFrom: string, monthDate: string): number {
  const gridStart = utcDate(dateFrom);
  gridStart.setUTCDate(gridStart.getUTCDate() - gridStart.getUTCDay());
  const firstOfMonth = utcDate(monthDate);
  return Math.floor((firstOfMonth.getTime() - gridStart.getTime()) / (7 * 24 * 60 * 60 * 1000));
}

function financialYearOptions(available: string[], selected: string): string[] {
  return [...new Set([selected, ...available])].sort((left, right) => right.localeCompare(left));
}

export function prioritizeActiveProjects<T extends { project_key: string }>(
  projects: T[],
  selectedProjects: Array<{ project_key: string; exact_seconds: number }> | undefined,
  selectedProjectKeys: string[] = [],
): T[] {
  if (!selectedProjects?.length && !selectedProjectKeys.length) return projects;
  const originalIndex = new Map(projects.map((project, index) => [project.project_key, index]));
  const selectedSeconds = new Map(
    (selectedProjects ?? []).map((project) => [project.project_key, project.exact_seconds]),
  );
  const selectedOrder = new Map(
    selectedProjectKeys.map((projectKey, index) => [projectKey, index]),
  );
  return [...projects].sort((left, right) => {
    const leftSelected = selectedOrder.get(left.project_key);
    const rightSelected = selectedOrder.get(right.project_key);
    if (leftSelected !== undefined && rightSelected === undefined) return -1;
    if (leftSelected === undefined && rightSelected !== undefined) return 1;
    if (leftSelected !== undefined && rightSelected !== undefined) {
      return leftSelected - rightSelected;
    }
    const leftSeconds = selectedSeconds.get(left.project_key);
    const rightSeconds = selectedSeconds.get(right.project_key);
    if (leftSeconds !== undefined && rightSeconds === undefined) return -1;
    if (leftSeconds === undefined && rightSeconds !== undefined) return 1;
    if (leftSeconds !== undefined && rightSeconds !== undefined && leftSeconds !== rightSeconds) {
      return rightSeconds - leftSeconds;
    }
    return (originalIndex.get(left.project_key) ?? 0) - (originalIndex.get(right.project_key) ?? 0);
  });
}

export function updateProjectSelection(
  selected: string[],
  projectKey: string,
  additive: boolean,
): string[] {
  if (!additive) {
    return selected.length === 1 && selected[0] === projectKey ? [] : [projectKey];
  }
  return selected.includes(projectKey)
    ? selected.filter((key) => key !== projectKey)
    : [...selected, projectKey];
}

export function financialYearForDate(value: string): string {
  const date = utcDate(value.slice(0, 10));
  const startYear = date.getUTCMonth() >= 6 ? date.getUTCFullYear() : date.getUTCFullYear() - 1;
  return `${startYear}-${String(startYear + 1).slice(-2)}`;
}

export function financialYearDates(financialYear: string): [string, string] {
  const startYear = Number(financialYear.replace(/^FY/i, "").split("-", 1)[0]);
  return [`${startYear}-07-01`, `${startYear + 1}-06-30`];
}

function financialYearMonths(dateFrom: string): Array<{ date: string; label: string }> {
  const formatter = new Intl.DateTimeFormat("en-AU", { month: "short", timeZone: "UTC" });
  const cursor = utcDate(dateFrom);
  return Array.from({ length: 12 }, () => {
    const result = { date: isoDate(cursor), label: formatter.format(cursor) };
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    return result;
  });
}

function utcDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}
