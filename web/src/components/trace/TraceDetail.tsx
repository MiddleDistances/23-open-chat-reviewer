import { ArrowLeft, Eye, ListTree, MessageSquareText, Route, Waypoints } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../api";
import type { ChatTrace } from "../../types";
import { ErrorNotice, Loading, PageHeader, formatDate, formatDuration, formatNumber, projectName } from "../Common";
import { TraceMinimap } from "./TraceMinimap";
import { TraceOccurrenceCard } from "./TraceOccurrenceCard";

export function TraceDetail({ sessionId }: { sessionId: number }) {
  const [expanded, setExpanded] = useState(false);
  const { data, loading, error } = useApi<ChatTrace>(`/api/sessions/${sessionId}/trace`);

  if (loading) return <Loading label="Building the chat evidence spine" />;
  if (error || !data) return <ErrorNotice message={error ?? "Chat trace not found"} />;

  const maximumAction = Math.max(1, ...data.summary.actions.map((item) => item.count));
  return (
    <>
      <div className="detail-back"><Link to="/trace"><ArrowLeft size={14} />All chat traces</Link></div>
      <PageHeader eyebrow="Automated chat trace" title={data.session.title || projectName(data.session.project)}>
        <Link className="button" to={`/sessions/${sessionId}`}><MessageSquareText size={15} />Exact transcript</Link>
      </PageHeader>

      <section className="trace-identity panel">
        <div><small>Chat ID</small><code>{data.session.external_id}</code></div>
        <div><small>Folder</small><strong>{data.session.cwd ?? data.session.project ?? "Unknown"}</strong></div>
        <div><small>Span</small><strong>{formatDate(data.session.started_at)} — {formatDate(data.session.ended_at)}</strong></div>
      </section>

      <section className="trace-summary-grid" aria-label="Chat trace summary">
        <div><strong>{formatNumber(data.summary.occurrences)}</strong><span>occurrences</span></div>
        <div><strong>{formatNumber(data.summary.tool_calls)}</strong><span>exact calls</span></div>
        <div className="summary-error"><strong>{formatNumber(data.summary.error_occurrences)}</strong><span>with errors</span></div>
        <div><strong>{formatNumber(data.summary.corrections)}</strong><span>correction markers</span></div>
        <div><strong>{formatDuration(data.summary.active_seconds)}</strong><span>gap-capped active time</span></div>
      </section>

      {data.occurrences.length > 0 && (
        <section className="trace-overview panel">
          <div className="panel-title"><div><span className="eyebrow">Overview strip</span><h2>Conversation evidence from start to finish</h2></div><span>{data.occurrences.length} visible occurrences</span></div>
          <TraceMinimap occurrences={data.occurrences} />
          <div className="trace-overview-legend"><span><i className="legend-discussion" />Discussion</span><span><i className="legend-attempt" />Attempt</span><span><i className="legend-result" />Result observed</span><span><i className="legend-error" />Error observed</span><span><b />User correction</span></div>
        </section>
      )}

      <div className="trace-view-toolbar">
        <div><Waypoints size={16} /><span>Chronological evidence spine</span></div>
        <div className="trace-view-toggle" aria-label="Trace detail level">
          <button className={!expanded ? "active" : ""} type="button" aria-pressed={!expanded} onClick={() => setExpanded(false)}><Eye size={14} />Condensed</button>
          <button className={expanded ? "active" : ""} type="button" aria-pressed={expanded} onClick={() => setExpanded(true)}><ListTree size={14} />Expanded calls</button>
        </div>
      </div>

      <div className="trace-layout">
        <section className="trace-spine" aria-label="Chronological chat occurrences">
          {data.occurrences.map((occurrence) => <TraceOccurrenceCard occurrence={occurrence} expanded={expanded} sessionId={sessionId} key={occurrence.id} />)}
          {data.truncated && <div className="trace-truncated">This trace shows {formatNumber(data.occurrences.length)} of {formatNumber(data.total_occurrences)} occurrences. Open the transcript for the remaining evidence.</div>}
        </section>
        <aside className="trace-analysis">
          <section className="panel">
            <span className="eyebrow">Call shape</span><h2>Action distribution</h2>
            <div className="trace-action-list">
              {data.summary.actions.map((item) => <div key={item.action}><span>{item.action}</span><i><b style={{ width: `${(item.count / maximumAction) * 100}%` }} /></i><strong>{formatNumber(item.count)}</strong></div>)}
            </div>
          </section>
          <section className="panel">
            <span className="eyebrow">Directly follows</span><h2>Common transitions</h2>
            <div className="trace-transition-list">
              {data.top_transitions.map((transition) => <div key={`${transition.from}-${transition.to}`}><span>{transition.from}</span><Route size={12} /><span>{transition.to}</span><strong>×{transition.count}</strong><small>{transition.occurrence_support} occurrences</small></div>)}
              {data.top_transitions.length === 0 && <p className="quiet">More than one call is needed to derive transitions.</p>}
            </div>
          </section>
          <p className="trace-method-note">{data.method_note}</p>
        </aside>
      </div>
    </>
  );
}
