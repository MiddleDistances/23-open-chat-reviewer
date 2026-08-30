import { AlertCircle, ArrowRight, CheckCircle2, MessageSquareWarning, TerminalSquare } from "lucide-react";
import { Link } from "react-router-dom";
import type { TraceOccurrence } from "../../types";
import { Badge, formatDate, formatDuration, formatNumber } from "../Common";

const CONDENSED_RUNS = 14;

export function TraceOccurrenceCard({ occurrence, expanded, sessionId }: { occurrence: TraceOccurrence; expanded: boolean; sessionId: number }) {
  const visibleRuns = expanded ? occurrence.call_runs : occurrence.call_runs.slice(0, CONDENSED_RUNS);
  const locallyHiddenRuns = occurrence.call_runs.length - visibleRuns.length;
  const totalHiddenRuns = occurrence.hidden_run_count + locallyHiddenRuns;
  const stateLabel = occurrence.evidence_state.replace(/-/g, " ");

  return (
    <article className={`trace-occurrence trace-state-${occurrence.evidence_state}`} id={`occurrence-${occurrence.id}`}>
      <div className="trace-occurrence-time">
        <time>{formatDate(occurrence.started_at, true)}</time>
        <span>{formatDuration(occurrence.active_seconds)} active</span>
      </div>
      <div className="trace-rail" aria-hidden="true"><i /></div>
      <div className="trace-occurrence-card">
        <header>
          <div className="trace-occurrence-labels">
            <Badge tone={occurrence.error_count ? "error" : "neutral"}>{stateLabel}</Badge>
            <span>Occurrence {occurrence.sequence_no + 1}</span>
            {occurrence.correction && <span className="correction-marker"><MessageSquareWarning size={13} />User correction</span>}
          </div>
          <strong>{formatNumber(occurrence.tool_call_count)} calls</strong>
        </header>
        <h2>{occurrence.signature.title}</h2>
        <p className="signature-basis">Provisional signature from {occurrence.signature.basis.replace(/-/g, " ")}</p>

        {occurrence.context && (
          <div className="trace-context">
            <small>Conversation context</small>
            <p>{occurrence.context}</p>
          </div>
        )}

        {(occurrence.signature.entities.length > 0 || occurrence.signature.errors.length > 0) && (
          <div className="trace-signals">
            {occurrence.signature.entities.map((entity) => <span key={`entity-${entity}`}>{entity}</span>)}
            {occurrence.signature.errors.slice(0, 2).map((error) => <span className="error-signal" key={`error-${error}`}><AlertCircle size={11} />{error}</span>)}
          </div>
        )}

        {occurrence.tool_call_count > 0 ? (
          <section className="trace-call-section">
            <div className="trace-call-heading"><TerminalSquare size={14} /><strong>Normalised call sequence</strong><span>exact calls, collapsed into consecutive runs</span></div>
            <div className="trace-call-runs">
              {visibleRuns.map((run) => (
                <div className={`trace-call-run action-${run.action} outcome-${run.outcome}`} key={`${run.first_event_id}-${run.last_event_id}-${run.operation}-${run.outcome}`}>
                  <small>{run.action}</small>
                  <span>{run.operation}</span>
                  {run.count > 1 && <b>×{run.count}</b>}
                  <i title={run.outcome}>{run.outcome === "error" ? <AlertCircle size={11} /> : run.outcome === "result" ? <CheckCircle2 size={11} /> : null}</i>
                </div>
              ))}
              {totalHiddenRuns > 0 && <span className="trace-hidden-runs">+{formatNumber(totalHiddenRuns)} more runs{occurrence.hidden_call_count ? ` · ${formatNumber(occurrence.hidden_call_count)} calls server-collapsed` : ""}</span>}
            </div>
          </section>
        ) : <p className="trace-no-calls">Discussion occurrence—no tool calls were observed.</p>}

        {occurrence.outcome && <div className="trace-outcome"><small>Conversation outcome</small><p>{occurrence.outcome}</p></div>}

        <footer>
          <Link to={`/episodes/${occurrence.id}`}>Open episode evidence <ArrowRight size={13} /></Link>
          <Link to={`/sessions/${sessionId}?event=${occurrence.first_event_id}`} className="trace-transcript-link">Open exact transcript <ArrowRight size={13} /></Link>
        </footer>
      </div>
    </article>
  );
}
