import { ChevronDown, ChevronRight, ExternalLink, TerminalSquare } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { EventRecord } from "../types";
import { Badge, formatDate } from "./Common";

export default function Transcript({ events }: { events: EventRecord[] }) {
  const [params] = useSearchParams();
  const focused = Number(params.get("event"));
  useEffect(() => {
    if (!focused) return;
    document.getElementById(`event-${focused}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focused, events]);
  return (
    <div className="transcript">
      {events.map((event) => <TranscriptEvent key={event.id} event={event} focused={event.id === focused} />)}
    </div>
  );
}

function TranscriptEvent({ event, focused }: { event: EventRecord; focused: boolean }) {
  const [expanded, setExpanded] = useState(focused || event.role === "user" || event.role === "assistant");
  const [rawOpen, setRawOpen] = useState(false);
  const role = event.role ?? event.subtype ?? event.event_type;
  return (
    <article id={`event-${event.id}`} className={`transcript-event role-${event.role ?? "other"} ${focused ? "focused" : ""}`}>
      <button className="event-header" onClick={() => setExpanded((value) => !value)}>
        {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        <span className="role-dot" />
        <strong>{role}</strong>
        {event.subtype && event.subtype !== role && <Badge>{event.subtype}</Badge>}
        <time>{formatDate(event.timestamp, true)}</time>
        <span className="line-reference">line {event.line_no.toLocaleString()}</span>
      </button>
      {expanded && (
        <div className="event-body">
          {event.parse_error && <pre className="error-block">{event.parse_error}</pre>}
          {event.units.map((unit) => (
            <section className={`unit unit-${unit.kind} ${unit.is_error ? "unit-error" : ""}`} key={unit.unit_key}>
              <div className="unit-label">{unit.kind}{unit.label ? ` · ${unit.label}` : ""}</div>
              <pre>{unit.text}</pre>
            </section>
          ))}
          <div className="event-footer">
            <button className="text-button" onClick={() => setRawOpen((value) => !value)}><TerminalSquare size={14} />Raw provenance</button>
            <a className="text-button" href={`/api/events/${event.id}/raw?as_text=true`} target="_blank" rel="noreferrer"><ExternalLink size={13} />Open raw source record</a>
          </div>
          {rawOpen && <RawProvenance event={event} />}
        </div>
      )}
    </article>
  );
}

function RawProvenance({ event }: { event: EventRecord }) {
  const sourceProvenance = event.source_provenance ?? {};
  return (
    <dl className="provenance-grid">
      <dt>Source</dt><dd>{event.source_path}</dd>
      <dt>Line</dt><dd>{event.line_no.toLocaleString()}</dd>
      {typeof sourceProvenance.project_root === "string" && <><dt>Project root</dt><dd>{sourceProvenance.project_root}</dd></>}
      {typeof sourceProvenance.evidence_sha256 === "string" && <><dt>Mapping hash</dt><dd><code>{sourceProvenance.evidence_sha256}</code></dd></>}
      <dt>Event key</dt><dd><code>{event.event_key}</code></dd>
    </dl>
  );
}
