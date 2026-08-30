import {
  Archive,
  CalendarClock,
  CheckCircle2,
  Download,
  FolderKanban,
  Tags,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, queryString, useApi } from "../api";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  Loading,
  PageHeader,
  formatDate,
  formatHours,
  formatNumber,
} from "../components/Common";
import {
  TimesheetCalendar,
  financialYearDates,
  financialYearForDate,
  type TimesheetIntervalRow,
} from "../components/timesheets/TimesheetCalendar";

interface Project {
  id: number;
  project_key: string;
  name: string;
  repository_url: string | null;
  is_unresolved: boolean;
  session_count: number;
  alias_count: number;
  default_activity: string | null;
  default_classification: string | null;
}

interface Activity {
  id: number;
  code: string;
  title: string;
  classification: string;
  reporting_period_start: string;
  reporting_period_end: string;
  description: string | null;
  uncertainty_or_hypothesis: string | null;
}

interface UnresolvedQueues {
  projects: unknown[];
  activities: unknown[];
  contributors: unknown[];
}

interface TrailItem {
  episode_id: number;
  episode_key: string;
  started_at: string | null;
  evidence_state: string;
  error_count: number;
  contributor: string | null;
  project: string | null;
  activity: string | null;
  classification: string;
  goal: string | null;
  outcome: string | null;
  raw_record_id: number;
  provenance_hash: string;
}

interface TimesheetSnapshot {
  id: number;
  snapshot_key: string;
  corpus_fingerprint: string;
  cutoff: string;
  algorithm_version: number;
  interval_count: number;
  total_seconds: number;
  ambiguity_count: number;
  completed_at: string;
}

interface TimesheetResponse {
  snapshot: TimesheetSnapshot | null;
  rows: TimesheetIntervalRow[];
}

interface ArchiveStatus {
  sources: number;
  revisions: number;
  raw_records: number;
  raw_payloads: number;
  length_mismatches: number;
  attention_revisions: number;
  pending_bytes: number;
  statuses: Record<string, number>;
  privacy: string;
}

type ArchiveView = "registry" | "trail" | "timesheets" | "status";

export default function WorkArchivePage() {
  const { pathname } = useLocation();
  const view: ArchiveView = pathname.includes("work-trail")
    ? "trail"
    : pathname.includes("timesheets")
      ? "timesheets"
      : pathname.includes("archive-status")
        ? "status"
        : "registry";

  const projects = useApi<Project[]>(view === "registry" ? "/api/projects" : null);
  const activities = useApi<Activity[]>(view === "registry" ? "/api/activities" : null);
  const unresolved = useApi<UnresolvedQueues>(
    view === "registry" ? "/api/registry/unresolved" : null,
  );
  const trail = useApi<TrailItem[]>(view === "trail" ? "/api/work-trail?limit=100" : null);
  const timesheets = useApi<TimesheetResponse>(view === "timesheets" ? "/api/timesheets?limit=1" : null);
  const archive = useApi<ArchiveStatus>(view === "status" ? "/api/archive-status" : null);

  const loading =
    projects.loading || activities.loading || unresolved.loading || trail.loading ||
    timesheets.loading || archive.loading;
  const error =
    projects.error || activities.error || unresolved.error || trail.error ||
    timesheets.error || archive.error;

  if (loading) return <Loading label="Reading the work archive" />;
  if (error) return <ErrorNotice message={error} />;
  if (view === "registry") {
    return (
      <RegistryView
        projects={projects.data ?? []}
        activities={activities.data ?? []}
        unresolved={unresolved.data}
        refresh={() => {
          projects.refresh();
          activities.refresh();
          unresolved.refresh();
        }}
      />
    );
  }
  if (view === "trail") return <TrailView items={trail.data ?? []} />;
  if (view === "timesheets") {
    return <TimesheetView data={timesheets.data} refresh={timesheets.refresh} />;
  }
  return <ArchiveStatusView data={archive.data} />;
}

function RegistryView({
  projects,
  activities,
  unresolved,
  refresh,
}: {
  projects: Project[];
  activities: Activity[];
  unresolved: UnresolvedQueues | null;
  refresh: () => void;
}) {
  const [rebuilding, setRebuilding] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function rebuild() {
    setRebuilding(true);
    setActionError(null);
    try {
      await api("/api/projects/rebuild", { method: "POST" });
      refresh();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRebuilding(false);
    }
  }

  const queueTotal =
    (unresolved?.projects.length ?? 0) +
    (unresolved?.activities.length ?? 0) +
    (unresolved?.contributors.length ?? 0);
  return (
    <>
      <PageHeader eyebrow="Work registry" title="Projects & categories">
        <button className="button" type="button" onClick={rebuild} disabled={rebuilding}>
          <RefreshCw size={14} /> {rebuilding ? "Resolving…" : "Rebuild aliases"}
        </button>
      </PageHeader>
      {actionError ? <ErrorNotice message={actionError} /> : null}
      <section className="archive-summary-grid">
        <Summary value={projects.length} label="canonical projects" icon={<FolderKanban />} />
        <Summary value={activities.length} label="optional work categories" icon={<Tags />} />
        <Summary value={queueTotal} label="unresolved assignments" icon={<TriangleAlert />} />
      </section>
      <div className="archive-two-column">
        <section className="panel archive-panel">
          <div className="panel-title"><div><span className="eyebrow">Canonical work</span><h2>Projects</h2></div></div>
          <div className="archive-card-list">
            {projects.map((project) => (
              <article key={project.project_key}>
                <div>
                  <strong>{project.name}</strong>
                  <small>{project.repository_url ?? "Path-derived identity awaiting resolution"}</small>
                </div>
                <div className="archive-card-meta">
                  <Badge tone={project.is_unresolved ? "partial" : "success"}>
                    {project.is_unresolved ? "unresolved" : "canonical"}
                  </Badge>
                  <span>{formatNumber(project.session_count)} chats</span>
                  <span>{formatNumber(project.alias_count)} aliases</span>
                  <code>{project.default_activity ?? "no default activity"}</code>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className="panel archive-panel">
          <div className="panel-title"><div><span className="eyebrow">Optional organization</span><h2>Work categories</h2></div></div>
          <div className="archive-card-list">
            {activities.map((activity) => (
              <article key={activity.code}>
                <div>
                  <strong><code>{activity.code}</code> · {activity.title}</strong>
                  <small>{activity.description ?? "No description recorded"}</small>
                </div>
                <div className="archive-card-meta">
                  <Badge tone={classificationTone(activity.classification)}>{activity.classification}</Badge>
                  <span>{formatDate(activity.reporting_period_start)} – {formatDate(activity.reporting_period_end)}</span>
                </div>
              </article>
            ))}
            {activities.length === 0 ? <EmptyState title="No categories registered"><span>The workload calendar works without categories. Add them through the API only if you want another grouping layer.</span></EmptyState> : null}
          </div>
        </section>
      </div>
    </>
  );
}

function TrailView({ items }: { items: TrailItem[] }) {
  return (
    <>
      <PageHeader eyebrow="Evidence timeline" title="Work trail" />
      <p className="archive-intro">Occurrences remain traceable to hash-verified raw records. Categories are optional organization aids and never change the underlying evidence.</p>
      <section className="panel archive-panel archive-table-wrap">
        <table className="archive-table">
          <thead><tr><th>Date</th><th>Project / activity</th><th>Evidence</th><th>State</th><th>Provenance</th></tr></thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.episode_key}>
                <td>{formatDate(item.started_at, true)}<small>{item.contributor ?? "Unresolved contributor"}</small></td>
                <td><strong>{item.project ?? "Unallocated"}</strong><small>{item.activity ?? "Unclassified"}</small></td>
                <td><Link to={`/episodes/${item.episode_id}`}>{item.goal ?? "Open occurrence evidence"}</Link><small>{item.outcome ?? `${item.error_count} observed errors`}</small></td>
                <td><Badge tone={classificationTone(item.classification)}>{item.classification}</Badge><small>{item.evidence_state}</small></td>
                <td><code title={item.provenance_hash}>{item.provenance_hash.slice(0, 12)}</code><small>raw {item.raw_record_id}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 ? <EmptyState title="No occurrence trail yet"><span>Run occurrence derivation, then assign projects and activities.</span></EmptyState> : null}
      </section>
    </>
  );
}

function TimesheetView({
  data,
  refresh,
}: {
  data: TimesheetResponse | null;
  refresh: () => void;
}) {
  const [building, setBuilding] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const snapshot = data?.snapshot;
  const [financialYear, setFinancialYear] = useState(() =>
    financialYearForDate(snapshot?.cutoff ?? new Date().toISOString()),
  );
  const [dateFrom, dateTo] = financialYearDates(financialYear);
  const exportHref = (format: "csv" | "markdown" | "json") =>
    `/api/timesheets/export?${queryString({ format, date_from: dateFrom, date_to: dateTo })}`;
  async function build() {
    setBuilding(true);
    setActionError(null);
    try {
      await api("/api/timesheets/build", { method: "POST" });
      refresh();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBuilding(false);
    }
  }
  return (
    <>
      <PageHeader eyebrow="Calculated activity intervals" title="Workload calendar">
        <button className="button button-primary" type="button" onClick={build} disabled={building}>
          <CalendarClock size={14} /> {building ? "Calculating…" : "Build snapshot"}
        </button>
      </PageHeader>
      {actionError ? <ErrorNotice message={actionError} /> : null}
      {snapshot ? (
        <>
          <section className="archive-summary-grid">
            <Summary value={formatHours(snapshot.total_seconds)} label="calculated hours" icon={<CalendarClock />} />
            <Summary value={snapshot.interval_count} label="non-overlapping intervals" icon={<CheckCircle2 />} />
            <Summary value={snapshot.ambiguity_count} label="ambiguous intervals" icon={<TriangleAlert />} />
          </section>
          <div className="archive-manifest">
            <div><span>Official complete snapshot</span><code>{snapshot.snapshot_key}</code></div>
            <div><span>Corpus fingerprint</span><code>{snapshot.corpus_fingerprint}</code></div>
            <div><span>Cutoff</span><strong>{formatDate(snapshot.cutoff, true)}</strong></div>
            <div><span>Reporting period</span><strong>FY {financialYear}</strong></div>
            <div className="archive-downloads">
              <a className="button" href={exportHref("csv")}><Download size={13} /> CSV</a>
              <a className="button" href={exportHref("markdown")}><Download size={13} /> Evidence</a>
              <a className="button" href={exportHref("json")}><Download size={13} /> Manifest</a>
            </div>
          </div>
          <TimesheetCalendar
            financialYear={financialYear}
            setFinancialYear={setFinancialYear}
          />
          <p className="archive-caveat">Chat and Git activity time is an evidence aid, not proof of continuous human labour.</p>
        </>
      ) : (
        <EmptyState title="No complete timesheet snapshot"><span>Build the first versioned interval calculation from canonical timestamped evidence.</span></EmptyState>
      )}
    </>
  );
}

function ArchiveStatusView({ data }: { data: ArchiveStatus | null }) {
  if (!data) return null;
  const healthy = data.length_mismatches === 0 && data.attention_revisions === 0;
  return (
    <>
      <PageHeader eyebrow="Sync health" title="Archive status" />
      <section className={`archive-health ${healthy ? "archive-health-good" : "archive-health-attention"}`}>
        {healthy ? <CheckCircle2 /> : <TriangleAlert />}
        <div><strong>{healthy ? "Archive evidence is internally consistent" : "Archive needs attention"}</strong><p>{data.privacy}</p></div>
      </section>
      <section className="archive-summary-grid">
        <Summary value={data.sources} label="source files" icon={<Archive />} />
        <Summary value={data.revisions} label="preserved revisions" icon={<RefreshCw />} />
        <Summary value={data.raw_records} label="exact source records" icon={<CheckCircle2 />} />
        <Summary value={data.raw_payloads} label="deduplicated payloads" icon={<FolderKanban />} />
      </section>
      <section className="panel archive-panel">
        <div className="panel-title"><div><span className="eyebrow">Revision states</span><h2>Synchronization health</h2></div></div>
        <div className="archive-status-list">
          {Object.entries(data.statuses).map(([status, count]) => <div key={status}><Badge tone={status === "complete" ? "success" : "partial"}>{status}</Badge><strong>{formatNumber(count)}</strong></div>)}
          <div><span>Pending bytes</span><strong>{formatNumber(data.pending_bytes)}</strong></div>
          <div><span>Length mismatches</span><strong>{formatNumber(data.length_mismatches)}</strong></div>
        </div>
      </section>
    </>
  );
}

function Summary({ value, label, icon }: { value: string | number; label: string; icon: React.ReactNode }) {
  return <div><span>{icon}</span><strong>{typeof value === "number" ? formatNumber(value) : value}</strong><small>{label}</small></div>;
}

function classificationTone(value: string | null): string {
  if (value === "core") return "success";
  if (value === "supporting") return "partial";
  if (value === "non-project") return "neutral";
  return "neutral";
}
