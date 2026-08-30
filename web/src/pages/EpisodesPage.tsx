import { ArrowLeft, ArrowUpRight, GitCompareArrows, Search } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { queryString, useApi } from "../api";
import AnnotationPanel from "../components/AnnotationPanel";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  Loading,
  PageHeader,
  ProviderOptions,
  formatDate,
  formatDuration,
  formatNumber,
  projectName,
} from "../components/Common";
import type { EpisodeDetail, EpisodeStats, EpisodeSummary } from "../types";

export default function EpisodesPage() {
  const { episodeId } = useParams();
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const listPath = episodeId
    ? null
    : `/api/episodes?${queryString({ q: query, provider, errors_only: errorsOnly, limit: 200 })}`;
  const detailPath = episodeId ? `/api/episodes/${episodeId}` : null;
  const { data: stats } = useApi<EpisodeStats>("/api/episodes/stats");
  const { data: episodes, loading, error } = useApi<EpisodeSummary[]>(listPath);
  const {
    data: episode,
    loading: detailLoading,
    error: detailError,
  } = useApi<EpisodeDetail>(detailPath);

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuery(input.trim());
  }

  if (episodeId) {
    return (
      <>
        <Link className="back-link" to="/episodes"><ArrowLeft size={14} />All episodes</Link>
        {detailLoading && <Loading label="Loading episode evidence" />}
        {detailError && <ErrorNotice message={detailError} />}
        {episode && (
          <>
            <PageHeader eyebrow={episode.evidence_state} title={episode.goal || "Inferred episode without an explicit goal"}>
              <Badge tone={episode.provider}>{episode.provider}</Badge>
            </PageHeader>
            <div className="episode-detail-grid">
              <section className="episode-document panel">
                <div className="episode-meta">
                  <span>{projectName(episode.project)}</span>
                  <span>{episode.attempt_count} attempts</span>
                  <span>{episode.error_count} errors</span>
                  <span>{formatDuration(episode.active_seconds)} active</span>
                </div>
                <pre>{episode.document}</pre>
                <div className="episode-provenance">
                  <Link to={`/sessions/${episode.session_id}?event=${episode.first_event_id}`}>
                    Open original session <ArrowUpRight size={13} />
                  </Link>
                  <span>Events {episode.first_event_id}–{episode.last_event_id}</span>
                </div>
                <details>
                  <summary>{episode.fingerprints.length} deterministic fingerprints</summary>
                  <div className="fingerprint-list">
                    {episode.fingerprints.map((item) => (
                      <div key={`${item.kind}-${item.value_hash}`}><Badge>{item.kind}</Badge><code>{item.value}</code></div>
                    ))}
                  </div>
                </details>
              </section>
              <aside><AnnotationPanel targetType="episode" targetKey={episode.episode_key} /></aside>
            </div>
          </>
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Derived evidence units" title="Review goals, attempts, results, and observed errors">
        <div className="map-count"><GitCompareArrows size={15} />{formatNumber(stats?.episodes)} episodes</div>
      </PageHeader>
      <form className="search-console" onSubmit={submit}>
        <Search size={19} />
        <input aria-label="Episode query" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Search episode goals, commands, errors, or outcomes…" />
        <select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}><ProviderOptions /></select>
        <label className="check-filter"><input type="checkbox" checked={errorsOnly} onChange={(event) => setErrorsOnly(event.target.checked)} />Observed errors only</label>
        <button className="button button-primary" type="submit">Search</button>
      </form>
      {stats && <div className="episode-stats"><span><strong>{formatNumber(stats.error_episodes)}</strong> error-bearing</span><span><strong>{formatNumber(stats.attempts)}</strong> attempts</span><span><strong>{formatDuration(stats.active_seconds)}</strong> gap-capped active time</span><span><strong>{formatNumber(stats.duplicate_events)}</strong> shared-prefix events removed</span></div>}
      {loading && <Loading label="Loading derived episodes" />}
      {error && <ErrorNotice message={error} />}
      {episodes && episodes.length === 0 && <EmptyState title="No matching episodes"><span>Change the evidence filters or derive episodes with <code>uv run chatreview episodes</code>.</span></EmptyState>}
      <div className="episode-list">
        {episodes?.map((item) => (
          <article className="result-card episode-card" key={item.episode_key}>
            <div className="result-meta"><Badge tone={item.provider}>{item.provider}</Badge><span>{projectName(item.project)}</span><time>{formatDate(item.started_at, true)}</time></div>
            <h2>{item.goal || "Inferred goal from attempt context"}</h2>
            <p>{item.document.slice(0, 700)}</p>
            <div className="result-footer"><span>{item.evidence_state} · {item.attempt_count} attempts · {item.error_count} errors · {formatDuration(item.active_seconds)}</span><Link to={`/episodes/${item.id}`}>Review episode <ArrowUpRight size={13} /></Link></div>
          </article>
        ))}
      </div>
    </>
  );
}
