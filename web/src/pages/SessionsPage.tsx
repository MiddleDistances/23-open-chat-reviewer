import { ArrowLeft, Filter, MessageSquareText, Search, Waypoints } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { queryString, useApi } from "../api";
import AnnotationPanel from "../components/AnnotationPanel";
import { Badge, EmptyState, ErrorNotice, Loading, PageHeader, ProviderOptions, formatDate, formatNumber, projectName } from "../components/Common";
import Transcript from "../components/Transcript";
import type { EventRecord, Session } from "../types";

export default function SessionsPage() {
  const { sessionId } = useParams();
  if (sessionId) return <SessionDetail sessionId={Number(sessionId)} />;
  return <SessionList />;
}

function SessionList() {
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("");
  const path = useMemo(() => `/api/sessions?${queryString({ q: query, provider, limit: 250 })}`, [query, provider]);
  const { data, loading, error } = useApi<Session[]>(path);
  return <>
    <PageHeader eyebrow="Chronological source" title="Sessions without assumed boundaries" />
    <div className="filter-bar"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by project, title, or session ID" /><Filter size={15} /><select value={provider} onChange={(event) => setProvider(event.target.value)}><ProviderOptions /></select></div>
    {loading && <Loading />}{error && <ErrorNotice message={error} />}
    <div className="session-table">
      {data?.map((session) => <Link to={`/sessions/${session.id}`} className="session-row" key={session.id}>
        <div className={`provider-monogram provider-${session.provider}`}>{session.provider.slice(0, 1).toUpperCase()}</div>
        <div className="session-primary"><strong>{session.title || projectName(session.project)}</strong><small>{session.external_id}</small></div>
        <Badge tone={session.provider}>{session.provider}</Badge><span>{formatDate(session.started_at)}</span><span>{formatNumber(session.event_count)} events</span><span>{formatNumber(session.text_unit_count)} texts</span>
      </Link>)}
    </div>
    {data?.length === 0 && <EmptyState title="No matching sessions">Change the provider or project filter.</EmptyState>}
  </>;
}

function SessionDetail({ sessionId }: { sessionId: number }) {
  const { data: session, loading, error } = useApi<Session & { metadata: Record<string, unknown> }>(`/api/sessions/${sessionId}`);
  const { data: events, loading: eventsLoading, error: eventsError } = useApi<EventRecord[]>(`/api/sessions/${sessionId}/events?limit=5000`);
  if (loading) return <Loading />;
  if (error || !session) return <ErrorNotice message={error ?? "Session not found"} />;
  return <>
    <div className="detail-back"><Link to="/sessions"><ArrowLeft size={14} />All sessions</Link></div>
    <PageHeader eyebrow={`${session.provider} session`} title={session.title || projectName(session.project)}>
      <Link className="button button-primary" to={`/trace/${sessionId}`}><Waypoints size={15} />Visualise chat</Link>
      <a className="button" href={`/api/export?format=markdown&session_id=${sessionId}`}><MessageSquareText size={15} />Export evidence</a>
    </PageHeader>
    <section className="session-summary panel"><div><small>Session ID</small><code>{session.external_id}</code></div><div><small>Workspace</small><strong>{session.cwd ?? session.project ?? "Unknown"}</strong></div><div><small>Span</small><strong>{formatDate(session.started_at)} — {formatDate(session.ended_at)}</strong></div><div><small>Scale</small><strong>{formatNumber(session.event_count)} events · {formatNumber(session.text_unit_count)} texts</strong></div></section>
    <div className="session-detail-grid"><section><div className="section-heading"><MessageSquareText size={16} /><h2>Indexed transcript</h2></div>{eventsLoading && <Loading />}{eventsError && <ErrorNotice message={eventsError} />}{events && <Transcript events={events} />}</section><aside><AnnotationPanel targetType="session" targetKey={session.session_key} /></aside></div>
  </>;
}
