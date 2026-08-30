import { Bot, Check, CircleAlert, LoaderCircle, Play, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, ErrorNotice, formatDate } from "../components/Common";

export type SummaryAgentId = "qwen" | "codex-cli" | "claude-cli" | "gemini-cli";

export interface SummaryAgentProvider {
  id: SummaryAgentId;
  label: string;
  installed: boolean;
  authenticated: boolean | null;
  detail: string;
}

export interface SummaryAgentRun {
  status: string;
  active: boolean;
  provider?: SummaryAgentId | null;
  message?: string | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  result?: {
    selected?: number;
    generated?: number;
    reused?: number;
    failed?: number;
  } | null;
}

export interface SummaryAgentStatus {
  selected: SummaryAgentId | null;
  providers: SummaryAgentProvider[];
  run: SummaryAgentRun;
  latest_run?: {
    status?: string;
    completed_at?: string | null;
    generated_count?: number;
    reused_count?: number;
    failed_count?: number;
    model_name?: string;
    selected_count?: number;
  } | null;
}

interface Props {
  status: SummaryAgentStatus | null;
  loading?: boolean;
  error?: string | null;
  onRun?: (provider: SummaryAgentId, days: number) => void | Promise<void>;
}

export default function SummaryAgentPanel({ status, loading = false, error, onRun }: Props) {
  const [selected, setSelected] = useState<SummaryAgentId | null>(status?.selected ?? null);
  const [days, setDays] = useState(30);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (status?.selected) setSelected(status.selected);
  }, [status?.selected]);

  const providers = status?.providers ?? [];
  const selectedProvider = providers.find((provider) => provider.id === selected);
  const active = Boolean(status?.run.active);

  async function run() {
    if (!selected || !onRun) return;
    setSubmitting(true);
    setActionError(null);
    try {
      await onRun(selected, days);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel setup-section summary-agent-panel" aria-labelledby="summary-agent-title">
      <div className="setup-section-heading">
        <div className="setup-section-number"><Sparkles size={17} aria-hidden="true" /></div>
        <div>
          <span className="eyebrow">Focus summaries</span>
          <h2 id="summary-agent-title">Choose the agent that makes the archive useful</h2>
          <p>Use local Qwen, or call a coding-agent CLI through the login already active on this machine.</p>
        </div>
      </div>

      {error || actionError ? <ErrorNotice message={error ?? actionError ?? "Summary agent error"} /> : null}

      <div className="summary-agent-grid" role="radiogroup" aria-label="Summary agent">
        {providers.map((provider) => {
          const ready = provider.installed && provider.authenticated !== false;
          const checked = provider.id === selected;
          return (
            <button
              className={`summary-agent-choice ${checked ? "selected" : ""}`}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={!provider.installed || active}
              key={provider.id}
              onClick={() => setSelected(provider.id)}
            >
              <span className="summary-agent-icon"><Bot size={18} aria-hidden="true" /></span>
              <span><strong>{provider.label}</strong><small>{provider.detail}</small></span>
              <Badge tone={ready ? "success" : provider.installed ? "warning" : "neutral"}>
                {ready ? <><Check size={11} aria-hidden="true" /> Ready</> : provider.installed ? "Sign in" : "Configure"}
              </Badge>
            </button>
          );
        })}
        {!loading && providers.length === 0 ? (
          <div className="setup-empty-card"><CircleAlert size={18} aria-hidden="true" /><p>No summary agents were detected.</p></div>
        ) : null}
      </div>

      <div className="summary-agent-actions">
        <label>
          <span>Conversation history</span>
          <select value={days} onChange={(event) => setDays(Number(event.target.value))} disabled={active}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </label>
        <button
          className="primary-button"
          type="button"
          disabled={!selectedProvider?.installed || selectedProvider?.authenticated === false || active || submitting}
          onClick={run}
        >
          {active || submitting ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
          {active ? "Summaries are running" : submitting ? "Starting…" : "Save and run summaries"}
        </button>
      </div>

      {status?.run.status && status.run.status !== "idle" ? (
        <div className={`summary-agent-progress ${status.run.status}`} aria-live="polite">
          <div><strong>{status.run.message ?? status.run.status}</strong><Badge tone={active ? "warning" : status.run.status === "complete" ? "success" : "neutral"}>{status.run.status}</Badge></div>
          {status.run.started_at ? <small>Started {formatDate(status.run.started_at, true)}</small> : null}
          {status.run.error ? <p>{status.run.error}</p> : null}
        </div>
      ) : status?.latest_run ? (
        <div className="summary-agent-progress complete">
          <div><strong>Last batch: {status.latest_run.generated_count ?? 0} generated, {status.latest_run.reused_count ?? 0} unchanged</strong><Badge tone="success">{status.latest_run.status ?? "complete"}</Badge></div>
          {status.latest_run.completed_at ? <small>Completed {formatDate(status.latest_run.completed_at, true)}</small> : null}
        </div>
      ) : null}

      <p className="summary-agent-security"><ShieldCheck size={14} aria-hidden="true" /> The app never reads or copies CLI tokens. It passes one bounded evidence packet over stdin in an empty temporary directory; tools are disabled for Claude and sandboxed read-only for Codex and Gemini.</p>
    </section>
  );
}
