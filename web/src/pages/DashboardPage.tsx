import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock3,
  FolderGit2,
  GitBranch,
  MapPin,
  MessageSquareText,
  Monitor,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../api";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  Loading,
  formatDate,
  formatNumber,
  projectName,
} from "../components/Common";
import type { ResumeState, ResumeSurface, ResumeSurfaceResponse, Session } from "../types";

type ResumeFilter = "open" | ResumeState | "all";

const FILTERS: Array<{ value: ResumeFilter; label: string }> = [
  { value: "open", label: "Open work" },
  { value: "decision", label: "Decisions" },
  { value: "ready", label: "Ready" },
  { value: "blocked", label: "Blocked" },
  { value: "waiting", label: "Waiting" },
  { value: "unclear", label: "Unclear" },
  { value: "done", label: "Done" },
  { value: "all", label: "All" },
];

export default function DashboardPage() {
  const [filter, setFilter] = useState<ResumeFilter>("open");
  const { data, loading, error } = useApi<ResumeSurfaceResponse>("/api/resume-surfaces?limit=200");
  const needsArchiveFallback = Boolean(data && data.surfaces.length === 0);
  const {
    data: recentSessions,
    loading: sessionsLoading,
    error: sessionsError,
  } = useApi<Session[]>(needsArchiveFallback ? "/api/sessions?limit=20" : null);

  if (loading) return <Loading label="Recovering recent work threads" />;
  if (error) return <ErrorNotice message={error} />;
  if (!data) return null;
  if (needsArchiveFallback) {
    return (
      <ArchiveFallback
        sessions={recentSessions}
        loading={sessionsLoading}
        error={sessionsError}
      />
    );
  }

  const visible = data.surfaces.filter((surface) => matchesFilter(surface, filter));
  const openCount = data.surfaces.filter((surface) => surface.current_state !== "done").length;

  return (
    <div className="resume-dashboard">
      <header className="resume-header">
        <div>
          <span className="resume-kicker">Resume work</span>
          <h1>Pick up where the work actually stopped.</h1>
          <p>
            Recent root conversations are grouped with their child agents, then reduced to the goal,
            current position, and next consequential move.
          </p>
        </div>
        <div className="resume-overview" aria-label={`${openCount} open work threads`}>
          <strong>{openCount}</strong>
          <span>open threads</span>
          <small>
            {data.latest_run
              ? `Refreshed ${formatRecency(data.latest_run.completed_at ?? data.latest_run.started_at)}`
              : "No summary batch recorded"}
          </small>
        </div>
      </header>

      <aside className="resume-method-note">
        <Sparkles size={17} aria-hidden="true" />
        <p>{data.method_note}</p>
      </aside>

      <nav className="resume-filters" aria-label="Filter work by current state">
        {FILTERS.map((item) => {
          const count = filterCount(data.surfaces, item.value);
          return (
            <button
              type="button"
              className={filter === item.value ? "active" : ""}
              aria-pressed={filter === item.value}
              onClick={() => setFilter(item.value)}
              key={item.value}
            >
              <span>{item.label}</span>
              <strong>{count}</strong>
            </button>
          );
        })}
      </nav>

      <div className="resume-list" aria-live="polite">
        {visible.map((surface) => (
          <ResumeCard surface={surface} key={surface.root_session_id} />
        ))}
        {visible.length === 0 && (
          <EmptyState title="Nothing in this view">
            Choose another state to see the rest of the recent work archive.
          </EmptyState>
        )}
      </div>
    </div>
  );
}

function ArchiveFallback({
  sessions,
  loading,
  error,
}: {
  sessions: Session[] | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div className="resume-dashboard">
      <header className="resume-header">
        <div>
          <span className="resume-kicker">Archive ready</span>
          <h1>Continue from a recent conversation.</h1>
          <p>
            The archive is populated. These are chronological PostgreSQL records; optional
            model-authored work summaries have not been enabled on this installation.
          </p>
        </div>
        <div
          className="resume-overview"
          aria-label={`${sessions?.length ?? 0} recent conversations shown`}
        >
          <strong>{sessions?.length ?? 0}</strong>
          <span>recent conversations</span>
          <small>Direct archive evidence</small>
        </div>
      </header>

      <aside className="resume-method-note">
        <MessageSquareText size={17} aria-hidden="true" />
        <p>
          Provider, project, timestamps, and counts come directly from the archive. Open any row
          to inspect its evidence trace.
        </p>
      </aside>

      {loading && <Loading label="Loading recent conversations" />}
      {error && <ErrorNotice message={error} />}
      {sessions && sessions.length > 0 && (
        <div className="session-table" aria-label="Recent archived conversations">
          {sessions.map((session) => (
            <Link to={`/trace/${session.id}`} className="session-row" key={session.id}>
              <div className={`provider-monogram provider-${session.provider}`}>
                {session.provider.slice(0, 1).toUpperCase()}
              </div>
              <div className="session-primary">
                <strong>{session.title || projectName(session.project)}</strong>
                <small>{session.external_id}</small>
              </div>
              <Badge tone={session.provider}>{session.provider}</Badge>
              <span>{formatDate(session.ended_at ?? session.started_at, true)}</span>
              <span>{formatNumber(session.event_count)} events</span>
              <span>{formatNumber(session.text_unit_count)} texts</span>
            </Link>
          ))}
        </div>
      )}
      {sessions?.length === 0 && (
        <EmptyState title="No archived conversations yet">
          Open Setup &amp; storage to discover this machine and start the first sync.
        </EmptyState>
      )}
    </div>
  );
}

function ResumeCard({ surface }: { surface: ResumeSurface }) {
  const location = surface.locations[0];
  const hasFollowUp = surface.research_directions.length > 0 || surface.open_loops.length > 0;

  return (
    <article className="resume-card">
      <div className="resume-card-topline">
        <span className={`resume-state resume-state-${surface.current_state}`}>
          {stateLabel(surface.current_state)}
        </span>
        <span className="resume-recency"><Clock3 size={14} />{formatRecency(surface.last_activity_at)}</span>
        <span className="resume-providers"><Bot size={14} />{surface.providers.join(" + ")}</span>
      </div>

      <div className="resume-card-title">
        <div>
          <span>Work thread</span>
          <h2>{surface.concept}</h2>
        </div>
        <span className={`resume-confidence resume-confidence-${surface.confidence}`}>
          {surface.confidence} confidence
        </span>
      </div>

      <section className="resume-goal">
        <span>Long-term goal</span>
        <p>{surface.long_term_goal}</p>
      </section>

      <div className="resume-location" aria-label="Recorded work location">
        <span><Monitor size={15} />{location?.machine_name ?? "Unknown machine"}</span>
        <span><FolderGit2 size={15} />{projectName(location?.project_name ?? surface.project_name)}</span>
        <span title={location?.cwd ?? undefined}><MapPin size={15} /><code>{location?.cwd ?? "Unknown path"}</code></span>
      </div>

      <div className="resume-body-grid">
        <section>
          <span className="resume-section-label">Where it stopped</span>
          <p className="resume-summary">{surface.summary}</p>
        </section>
        <section>
          <span className="resume-section-label">Next moves</span>
          {surface.next_moves.length > 0 ? (
            <ol className="resume-next-moves">
              {surface.next_moves.map((move, index) => <li key={`${index}-${move}`}>{move}</li>)}
            </ol>
          ) : (
            <p className="resume-complete"><CheckCircle2 size={16} />No remaining action inferred.</p>
          )}
        </section>
      </div>

      {surface.next_decision && (
        <section className="resume-decision">
          <span>Decision to make</span>
          <p>{surface.next_decision}</p>
        </section>
      )}

      {hasFollowUp && (
        <div className="resume-follow-up">
          {surface.research_directions.length > 0 && (
            <section>
              <span>Research directions</span>
              <ul>{surface.research_directions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            </section>
          )}
          {surface.open_loops.length > 0 && (
            <section>
              <span>Open loops</span>
              <ul>{surface.open_loops.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            </section>
          )}
        </div>
      )}

      <footer className="resume-card-footer">
        <span><GitBranch size={14} />{surface.repository_url ?? surface.project_name ?? "Unallocated project"}</span>
        <Link to={`/trace/${surface.root_session_id}`}>
          Open evidence <ArrowRight size={15} />
        </Link>
      </footer>
    </article>
  );
}

function matchesFilter(surface: ResumeSurface, filter: ResumeFilter): boolean {
  if (filter === "all") return true;
  if (filter === "open") return surface.current_state !== "done";
  return surface.current_state === filter;
}

function filterCount(surfaces: ResumeSurface[], filter: ResumeFilter): number {
  return surfaces.filter((surface) => matchesFilter(surface, filter)).length;
}

function stateLabel(state: ResumeState): string {
  return state === "decision" ? "Decision" : `${state.charAt(0).toUpperCase()}${state.slice(1)}`;
}

function formatRecency(value: string | null): string {
  if (!value) return "at an unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return formatDate(value, true);
  const seconds = Math.round((date.getTime() - Date.now()) / 1_000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(seconds) < 90) return formatter.format(seconds, "second");
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 90) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 36) return formatter.format(hours, "hour");
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 45) return formatter.format(days, "day");
  return formatDate(value, true);
}
