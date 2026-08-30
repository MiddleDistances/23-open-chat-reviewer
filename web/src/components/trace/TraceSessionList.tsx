import { ArrowRight, Filter, Search, Waypoints } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { queryString, useApi } from "../../api";
import { Badge, EmptyState, ErrorNotice, Loading, PageHeader, ProviderOptions, formatDate, formatNumber, projectName } from "../Common";
import type { Session } from "../../types";

export function TraceSessionList() {
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("");
  const path = useMemo(
    () => `/api/sessions?${queryString({ q: query, provider, limit: 250 })}`,
    [query, provider],
  );
  const { data, loading, error } = useApi<Session[]>(path);

  return (
    <>
      <PageHeader eyebrow="Single-chat visualiser" title="Choose a conversation to trace" />
      <section className="trace-picker-intro">
        <Waypoints size={20} />
        <div>
          <strong>Follow one chat from discussion to evidence</strong>
          <p>Occurrences stay chronological. Repeated calls collapse into readable runs, while every card links back to the exact episode and transcript.</p>
        </div>
      </section>
      <div className="filter-bar">
        <Search size={16} />
        <input aria-label="Filter trace sessions" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by folder, title, or chat ID" />
        <Filter size={15} />
        <select aria-label="Trace provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
          <ProviderOptions />
        </select>
      </div>
      {loading && <Loading label="Loading conversations" />}
      {error && <ErrorNotice message={error} />}
      <div className="trace-session-list">
        {data?.map((session) => (
          <Link to={`/trace/${session.id}`} className="trace-session-card" key={session.id}>
            <div className={`provider-monogram provider-${session.provider}`}>{session.provider.slice(0, 1).toUpperCase()}</div>
            <div>
              <strong>{session.title || projectName(session.project)}</strong>
              <small>{projectName(session.cwd ?? session.project)} · {session.external_id}</small>
            </div>
            <Badge tone={session.provider}>{session.provider}</Badge>
            <span>{formatDate(session.started_at)}</span>
            <span>{formatNumber(session.event_count)} events</span>
            <ArrowRight size={15} />
          </Link>
        ))}
      </div>
      {data?.length === 0 && <EmptyState title="No matching chats">Change the folder, chat ID, or provider filter.</EmptyState>}
    </>
  );
}
