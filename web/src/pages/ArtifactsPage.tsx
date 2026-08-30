import { AlertOctagon, Code2, File, Search, Terminal } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { queryString, useApi } from "../api";
import { Badge, EmptyState, ErrorNotice, Loading, PageHeader, formatDate, projectName } from "../components/Common";

interface Artifact { id: number; kind: string; label: string | null; value: string; value_hash: string; event_id: number; timestamp: string | null; session_id: number | null; provider: string | null; project: string | null; }

const kinds = [{ value: "", label: "All evidence", icon: Code2 }, { value: "command", label: "Commands", icon: Terminal }, { value: "error-signature", label: "Errors", icon: AlertOctagon }, { value: "path", label: "Paths", icon: File }, { value: "code-block", label: "Code blocks", icon: Code2 }];

export default function ArtifactsPage() {
  const [kind, setKind] = useState(""); const [query, setQuery] = useState("");
  const { data, loading, error } = useApi<Artifact[]>(`/api/artifacts?${queryString({ kind, q: query, limit: 500 })}`);
  return <><PageHeader eyebrow="Structured transcript evidence" title="Commands, errors, code and paths" />
    <div className="artifact-layout"><aside className="artifact-kinds">{kinds.map(({ value, label, icon: Icon }) => <button className={kind === value ? "active" : ""} onClick={() => setKind(value)} key={value}><Icon size={15} />{label}</button>)}</aside><section><div className="filter-bar"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter extracted evidence" /></div>{loading && <Loading />}{error && <ErrorNotice message={error} />}<div className="artifact-list">{data?.map((item) => <article className="artifact-card" key={item.id}><div className="artifact-meta"><Badge tone={item.provider ?? "neutral"}>{item.provider ?? "unknown"}</Badge><strong>{item.kind}</strong>{item.label && <span>{item.label}</span>}<time>{formatDate(item.timestamp, true)}</time></div><pre>{item.value}</pre><div className="artifact-footer"><span>{projectName(item.project)}</span>{item.session_id && <Link to={`/sessions/${item.session_id}?event=${item.event_id}`}>Source event</Link>}</div></article>)}</div>{data?.length === 0 && <EmptyState title="No extracted evidence">Try another evidence type or search term.</EmptyState>}</section></div>
  </>;
}
