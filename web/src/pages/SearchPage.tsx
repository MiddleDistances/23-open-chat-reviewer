import { ArrowUpRight, Braces, CalendarDays, Search as SearchIcon, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { queryString, useApi } from "../api";
import { Badge, EmptyState, ErrorNotice, Highlight, Loading, PageHeader, ProviderOptions, formatDate, projectName } from "../components/Common";
import type { SearchResponse, SemanticRun } from "../types";

export type SearchTimeRange = "7d" | "30d" | "90d" | "365d" | "all" | "custom";

export function searchDateRange(range: SearchTimeRange, today = new Date()): { dateFrom: string; dateTo: string } {
  if (range === "all" || range === "custom") return { dateFrom: "", dateTo: "" };
  const days = Number(range.slice(0, -1));
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const start = new Date(end);
  start.setDate(start.getDate() - days + 1);
  const format = (value: Date) => [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
  return { dateFrom: format(start), dateTo: format(end) };
}

export default function SearchPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [provider, setProvider] = useState("");
  const [runKey, setRunKey] = useState("");
  const [timeRange, setTimeRange] = useState<SearchTimeRange>("30d");
  const [customDateFrom, setCustomDateFrom] = useState("");
  const [customDateTo, setCustomDateTo] = useState("");
  const selectedDates = timeRange === "custom"
    ? { dateFrom: customDateFrom, dateTo: customDateTo }
    : searchDateRange(timeRange);
  const { data: semanticRuns } = useApi<SemanticRun[]>("/api/semantic-runs");
  const path = query ? `/api/search?${queryString({
    q: query,
    mode,
    provider,
    run_key: runKey,
    date_from: selectedDates.dateFrom,
    date_to: selectedDates.dateTo,
    limit: 50,
  })}` : null;
  const { data, loading, error } = useApi<SearchResponse>(path);
  function submit(event: FormEvent) { event.preventDefault(); setQuery(input.trim()); }
  return (
    <>
      <PageHeader eyebrow="Hybrid retrieval" title="Find where the same problem resurfaced" />
      <form className="search-console" onSubmit={submit}>
        <SearchIcon size={19} />
        <input aria-label="Evidence query" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Search an error, goal, file, method, or idea…" autoFocus />
        <select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}><ProviderOptions /></select>
        <select aria-label="Search mode" value={mode} onChange={(event) => setMode(event.target.value)}><option value="hybrid">Hybrid</option><option value="lexical">Exact text</option><option value="semantic">Semantic</option></select>
        <select aria-label="Semantic run" value={runKey} onChange={(event) => setRunKey(event.target.value)} disabled={mode === "lexical"}>
          <option value="">Conversation run (default)</option>
          {semanticRuns?.filter((run) => run.status === "complete").map((run) => <option key={run.run_key} value={run.run_key}>{run.profile} · {run.chunk_count.toLocaleString()} · {run.freshness}</option>)}
        </select>
        <button className="button button-primary" type="submit">Search</button>
        <div className="search-time-controls" aria-label="Search date constraints">
          <CalendarDays size={15} aria-hidden="true" />
          <label>
            <span className="sr-only">Search time range</span>
            <select id="search-time-range" aria-label="Search time range" value={timeRange} onChange={(event) => setTimeRange(event.target.value as SearchTimeRange)}>
              <option value="7d">Recent 7 days</option>
              <option value="30d">Recent 30 days</option>
              <option value="90d">Recent 90 days</option>
              <option value="365d">Recent year</option>
              <option value="all">All time</option>
              <option value="custom">Custom dates</option>
            </select>
          </label>
          {timeRange === "custom" && <>
            <label><span>From</span><input id="search-date-from" aria-label="Search date from" type="date" value={customDateFrom} max={customDateTo || undefined} onChange={(event) => setCustomDateFrom(event.target.value)} /></label>
            <label><span>To</span><input id="search-date-to" aria-label="Search date to" type="date" value={customDateTo} min={customDateFrom || undefined} onChange={(event) => setCustomDateTo(event.target.value)} /></label>
          </>}
          <small>{selectedDates.dateFrom && selectedDates.dateTo ? `${selectedDates.dateFrom} to ${selectedDates.dateTo}` : "Every archived date"}</small>
        </div>
      </form>
      {!query && <EmptyState title="Start with a concrete trace"><span>Try an error message, a recurring objective, a source path, or the name of an approach that may have been repeated.</span></EmptyState>}
      {loading && <Loading label="Searching indexed evidence" />}
      {error && <ErrorNotice message={error} />}
      {data && <div className="search-results-grid">
        {mode !== "semantic" && <ResultColumn title="Exact evidence" icon={<Braces size={16} />} count={data.lexical.length}>
          {data.lexical.map((item) => <article className="result-card" key={item.unit_key}>
            <div className="result-meta"><Badge tone={item.provider ?? "neutral"}>{item.provider ?? "unknown"}</Badge><span>{projectName(item.project)}</span><time>{formatDate(item.timestamp, true)}</time></div>
            <p className="result-snippet"><Highlight html={item.snippet} /></p>
            <div className="result-footer"><span>{item.role ?? item.event_type} · {item.kind} · line {item.line_no.toLocaleString()}</span>{item.session_id && <Link to={`/sessions/${item.session_id}?event=${item.event_id}`}>Open evidence <ArrowUpRight size={13} /></Link>}</div>
          </article>)}
        </ResultColumn>}
        {mode !== "lexical" && <ResultColumn title={`Semantic neighbours · ${data.semantic[0]?.semantic_profile ?? "conversation"}`} icon={<Sparkles size={16} />} count={data.semantic.length} wide={mode === "semantic"}>
          {data.semantic_error && <div className="semantic-hint">{data.semantic_error}<code>uv sync --extra semantic && uv run chatreview derive</code></div>}
          {data.semantic.map((item) => <article className="result-card semantic-card" key={item.window_id}>
            <div className="result-meta"><Badge tone={item.provider}>{item.provider}</Badge><span>{projectName(item.project)}</span><strong>{(item.semantic_score * 100).toFixed(1)}%</strong></div>
            <p className="result-snippet">{item.snippet}</p>
            <div className="result-footer"><span>Cluster {item.cluster_id} · {item.episode_id ? "episode" : "window"} {item.sequence_no}</span><Link to={item.episode_id ? `/episodes/${item.episode_id}` : `/sessions/${item.session_id}?event=${item.first_event_id}`}>Open context <ArrowUpRight size={13} /></Link></div>
          </article>)}
        </ResultColumn>}
      </div>}
    </>
  );
}

function ResultColumn({ title, icon, count, wide = false, children }: { title: string; icon: React.ReactNode; count: number; wide?: boolean; children: React.ReactNode }) {
  return <section className={`result-column ${wide ? "wide" : ""}`}><div className="result-column-title">{icon}<h2>{title}</h2><span>{count}</span></div><div className="result-stack">{children}{count === 0 && <p className="quiet">No matching evidence in this retrieval layer.</p>}</div></section>;
}
