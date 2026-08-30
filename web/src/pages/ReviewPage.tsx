import { CheckCircle2, Plus, Tag } from "lucide-react";
import { FormEvent, useState } from "react";
import { api, queryString, useApi } from "../api";
import { Badge, ErrorNotice, Loading, PageHeader, formatDate, formatNumber } from "../components/Common";
import type { Annotation, Label } from "../types";

export default function ReviewPage() {
  const [filter, setFilter] = useState(""); const [newLabel, setNewLabel] = useState("");
  const { data: labels, refresh: refreshLabels } = useApi<Label[]>("/api/labels");
  const { data: annotations, loading, error, refresh: refreshAnnotations } = useApi<Annotation[]>(`/api/annotations?${queryString({ label: filter, limit: 1000 })}`);
  async function createLabel(event: FormEvent) { event.preventDefault(); if (!newLabel.trim()) return; await api("/api/labels", { method: "POST", body: JSON.stringify({ name: newLabel.trim().toLowerCase().replace(/\s+/g, "-"), color: "#8b5cf6" }) }); setNewLabel(""); refreshLabels(); }
  async function remove(id: number) { await api(`/api/annotations/${id}`, { method: "DELETE" }); refreshAnnotations(); refreshLabels(); }
  return <><PageHeader eyebrow="Human judgement layer" title="Build a review taxonomy from evidence" />
    <div className="review-grid"><aside className="panel label-panel"><div className="section-heading"><Tag size={16} /><h2>Labels</h2></div><button className={!filter ? "label-filter active" : "label-filter"} onClick={() => setFilter("")}><span>All annotations</span><strong>{formatNumber(labels?.reduce((sum, item) => sum + item.annotation_count, 0))}</strong></button>{labels?.map((item) => <button className={filter === item.name ? "label-filter active" : "label-filter"} onClick={() => setFilter(item.name)} key={item.id}><i style={{ background: item.color }} /><span>{item.name}</span><strong>{item.annotation_count}</strong></button>)}<form className="new-label" onSubmit={(event) => void createLabel(event)}><input value={newLabel} onChange={(event) => setNewLabel(event.target.value)} placeholder="New label" /><button title="Create label"><Plus size={15} /></button></form></aside><section><div className="review-heading"><div><span className="eyebrow">{filter || "All labels"}</span><h2>{formatNumber(annotations?.length)} review records</h2></div></div>{loading && <Loading />}{error && <ErrorNotice message={error} />}<div className="review-list">{annotations?.map((item) => <article className="review-card" key={item.id}><div className="review-card-top">{item.label ? <span className="label-chip" style={{ "--label-color": item.color ?? "#64748b" } as React.CSSProperties}>{item.label}</span> : <Badge>note</Badge>}<span>{item.target_type}</span><code>{item.target_key.slice(0, 16)}…</code><time>{formatDate(item.updated_at, true)}</time></div>{item.note && <p>{item.note}</p>}<div className="review-card-footer"><span><CheckCircle2 size={14} />{item.review_state}</span><button className="text-button danger" onClick={() => void remove(item.id)}>Remove</button></div></article>)}</div></section></div>
  </>;
}
