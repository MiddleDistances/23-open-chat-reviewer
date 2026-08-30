import { Check, Plus, Tag, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, queryString, useApi } from "../api";
import type { Annotation, Label } from "../types";
import { ErrorNotice, Loading } from "./Common";

export default function AnnotationPanel({ targetType, targetKey }: { targetType: "session" | "event" | "window" | "episode"; targetKey: string }) {
  const path = `/api/annotations?${queryString({ target_type: targetType, target_key: targetKey })}`;
  const { data: annotations, loading, error, refresh } = useApi<Annotation[]>(path);
  const { data: labels } = useApi<Label[]>("/api/labels");
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [reviewState, setReviewState] = useState("unreviewed");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      await api("/api/annotations", {
        method: "POST",
        body: JSON.stringify({
          target_type: targetType,
          target_key: targetKey,
          label: label || null,
          note: note || null,
          review_state: reviewState,
        }),
      });
      setNote("");
      refresh();
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number) {
    await api(`/api/annotations/${id}`, { method: "DELETE" });
    refresh();
  }

  return (
    <section className="annotation-panel">
      <div className="section-heading"><Tag size={16} /><h3>Review notes</h3></div>
      {loading && <Loading label="Loading notes" />}
      {error && <ErrorNotice message={error} />}
      <div className="annotation-list">
        {annotations?.map((item) => (
          <article className="annotation" key={item.id}>
            <div>
              {item.label && <span className="label-chip" style={{ "--label-color": item.color ?? "#64748b" } as React.CSSProperties}>{item.label}</span>}
              <span className="review-state"><Check size={12} />{item.review_state}</span>
            </div>
            {item.note && <p>{item.note}</p>}
            <button className="icon-button" onClick={() => void remove(item.id)} title="Delete annotation"><Trash2 size={14} /></button>
          </article>
        ))}
      </div>
      <div className="annotation-form">
        <div className="form-row">
          <select value={label} onChange={(event) => setLabel(event.target.value)} aria-label="Label">
            <option value="">No label</option>
            {labels?.map((item) => <option key={item.id} value={item.name}>{item.name}</option>)}
          </select>
          <select value={reviewState} onChange={(event) => setReviewState(event.target.value)} aria-label="Review state">
            <option value="unreviewed">Unreviewed</option>
            <option value="reviewing">Reviewing</option>
            <option value="reviewed">Reviewed</option>
          </select>
        </div>
        <textarea aria-label="Evidence note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="What was missed, repeated, or finally resolved?" rows={3} />
        {saveError && <ErrorNotice message={saveError} />}
        <button className="button button-primary" onClick={() => void save()} disabled={saving || (!label && !note)}>
          <Plus size={15} />{saving ? "Saving…" : "Add to review"}
        </button>
      </div>
    </section>
  );
}
