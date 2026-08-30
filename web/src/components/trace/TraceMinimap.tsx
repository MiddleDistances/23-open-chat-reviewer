import type { TraceOccurrence } from "../../types";

export function TraceMinimap({ occurrences }: { occurrences: TraceOccurrence[] }) {
  return (
    <nav className="trace-minimap" aria-label="Chat occurrence overview">
      {occurrences.map((occurrence) => (
        <a
          className={`trace-map-segment trace-state-${occurrence.evidence_state} ${occurrence.correction ? "has-correction" : ""}`}
          href={`#occurrence-${occurrence.id}`}
          key={occurrence.id}
          style={{ flexGrow: Math.min(6, 1 + Math.log2(occurrence.tool_call_count + 1)) }}
          title={`${occurrence.signature.title} · ${occurrence.tool_call_count} calls`}
        >
          <span className="sr-only">Occurrence {occurrence.sequence_no + 1}: {occurrence.signature.title}</span>
        </a>
      ))}
    </nav>
  );
}
