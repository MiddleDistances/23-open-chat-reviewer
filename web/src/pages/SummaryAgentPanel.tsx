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
  onConfigure?: (provider: SummaryAgentId) => void;
}

export default function SummaryAgentPanel({ status, loading = false, error, onRun, onConfigure }: Props) {
  const [selected, setSelected] = useState<SummaryAgentId | null>(status?.selected ?? null);
  const [days, setDays] = useState(30);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    setSelected(status?.selected ?? null);
  }, [status?.selected]);

  const providers = status?.providers ?? [];
  const selectedProvider = providers.find((provider) => provider.id === selected);
  const runState = status?.run ?? null;
  const latestRun = status?.latest_run ?? null;
  const active = Boolean(runState?.active);
  const runTimestamp = Date.parse(runState?.finished_at ?? runState?.started_at ?? "");
  const latestTimestamp = Date.parse(latestRun?.completed_at ?? "");
  const showRunState = Boolean(
    runState?.status
    && runState.status !== "idle"
    && (
      active
      || !latestRun
      || !Number.isFinite(runTimestamp)
      || !Number.isFinite(latestTimestamp)
      || runTimestamp >= latestTimestamp
    ),
  );

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
          <span className="eyebrow">Optional</span>
          <h2 id="summary-agent-title">Summaries</h2>
          <p>Choose a provider and how much recent work to summarise.</p>
        </div>
      </div>

      {error || actionError ? <ErrorNotice message={error ?? actionError ?? "Summary agent error"} /> : null}

      <div className="summary-agent-grid" role="radiogroup" aria-label="Summary agent">
        {providers.map((provider) => {
          const ready = provider.installed && provider.authenticated !== false;
          const checked = provider.id === selected;
          const canConfigure = !provider.installed && provider.id === "qwen" && Boolean(onConfigure);
          return (
            <button
              className={`summary-agent-choice ${checked ? "selected" : ""}`}
              id={`summary-agent-${provider.id}`}
              data-action-id={`summary.agent.select.${provider.id}`}
              type="button"
              role="radio"
              aria-checked={checked}
              disabled={(!provider.installed && !canConfigure) || active}
              key={provider.id}
              onClick={() => {
                if (canConfigure) {
                  onConfigure?.(provider.id);
                  return;
                }
                setSelected(provider.id);
              }}
            >
              <span className="summary-agent-icon"><Bot size={18} aria-hidden="true" /></span>
              <span><strong>{provider.label}</strong><small>{provider.detail}</small></span>
              <Badge tone={ready ? "success" : provider.installed ? "warning" : "neutral"}>
                {ready ? <><Check size={11} aria-hidden="true" /> Ready</> : provider.installed ? "Sign in" : "Configure"}
              </Badge>
            </button>
          );
        })}
        {loading ? (
          <div className="setup-empty-card" role="status" aria-live="polite">
            <LoaderCircle className="setup-spin" size={18} aria-hidden="true" />
            <p>Checking available providers…</p>
          </div>
        ) : providers.length === 0 ? (
          <div className="setup-empty-card"><CircleAlert size={18} aria-hidden="true" /><p>No summary agents were detected.</p></div>
        ) : null}
      </div>

      <div className="summary-agent-actions">
        <label htmlFor="summary-history-window">
          <span>Summary window</span>
          <select id="summary-history-window" data-action-id="summary.scope.days" value={days} onChange={(event) => setDays(Number(event.target.value))} disabled={active}>
            <option value={7}>Past 7 days</option>
            <option value={30}>Past 30 days</option>
            <option value={90}>Past 90 days</option>
            <option value={365}>Past year</option>
          </select>
          <small>Only summaries are affected; archive history is unchanged.</small>
        </label>
        <button
          className="primary-button"
          id="summary-run"
          data-action-id="summary.run.start"
          type="button"
          disabled={!selectedProvider?.installed || selectedProvider?.authenticated === false || active || submitting}
          onClick={run}
        >
          {active || submitting ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}
          {active ? "Summaries are running" : submitting ? "Starting…" : "Run summaries"}
        </button>
      </div>

      {showRunState && runState ? (
        <div className={`summary-agent-progress ${runState.status}`} aria-live="polite">
          <div><strong>{runState.message ?? runState.status}</strong><Badge tone={active ? "warning" : runState.status === "complete" ? "success" : "neutral"}>{runState.status}</Badge></div>
          {runState.started_at ? <small>Started {formatDate(runState.started_at, true)}</small> : null}
          {runState.error ? <p>{runState.error}</p> : null}
        </div>
      ) : latestRun ? (
        <div className="summary-agent-progress complete">
          <div><strong>Last batch{latestRun.model_name ? ` · ${latestRun.model_name}` : ""}: {latestRun.generated_count ?? 0} generated, {latestRun.reused_count ?? 0} unchanged</strong><Badge tone="success">{latestRun.status ?? "complete"}</Badge></div>
          {latestRun.completed_at ? <small>Completed {formatDate(latestRun.completed_at, true)}</small> : null}
        </div>
      ) : null}

      <p className="summary-agent-security"><ShieldCheck size={14} aria-hidden="true" /> CLI credentials stay with the CLI. ChatReviewer sends only a bounded evidence packet.</p>
    </section>
  );
}
