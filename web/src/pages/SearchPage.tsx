import { ArrowUpRight, Braces, Search as SearchIcon, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { queryString, useApi } from "../api";
import { Badge, EmptyState, ErrorNotice, Highlight, Loading, PageHeader, ProviderOptions, formatDate, projectName } from "../components/Common";
import type { SearchResponse, SemanticRun } from "../types";

export default function SearchPage() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [provider, setProvider] = useState("");
  const [runKey, setRunKey] = useState("");
  const { data: semanticRuns } = useApi<SemanticRun[]>("/api/semantic-runs");
  const path = query ? `/api/search?${queryString({ q: query, mode, provider, run_key: runKey, limit: 50 })}` : null;
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
