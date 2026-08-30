import {
  BookOpen,
  CalendarDays,
  Check,
  ChevronRight,
  CloudCog,
  Database,
  HardDrive,
  Info,
  LoaderCircle,
  Monitor,
  Play,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Badge,
  ErrorNotice,
  PageHeader,
  formatBytes,
  formatDate,
  formatDuration,
  formatNumber,
} from "../components/Common";

export type SetupProvider = "codex" | "claude" | "gemini";

export interface SetupConfig {
  /** Inclusive lower bound. An empty value means the oldest available record. */
  historyStart: string;
  /** Inclusive upper bound. An empty value means the newest available record. */
  historyEnd: string;
  providers: SetupProvider[];
  includeGitMetadata: boolean;
  /** Keep exact encrypted provider payloads in the raw evidence archive. */
  preserveEncryptedReasoning: boolean;
  /** Make readable reasoning text eligible for lexical/full-text search. */
  includeReadableReasoningInSearch: boolean;
  /** Add readable reasoning text to the semantic/vector projection. */
  includeReasoningInProjection: boolean;
}

export interface SetupSourceRoot {
  provider: SetupProvider | "git";
  path: string;
  discovered?: boolean;
  recordCount?: number;
}

export type SetupMachineStatus = "current" | "connected" | "needs-setup" | "offline" | "syncing";

export interface SetupMachine {
  id: string;
  name: string;
  status: SetupMachineStatus;
  platform?: string | null;
  sourceRoots: SetupSourceRoot[];
  lastSeenAt?: string | null;
  eventCount?: number | null;
  note?: string | null;
}

export interface SetupEstimate {
  sourceCount?: number;
  sessionCount?: number;
  eventCount?: number;
  rawBytes?: number;
  encryptedReasoningBytes?: number;
  readableReasoningBytes?: number;
  semanticBytes?: number;
  semanticWindowCount?: number;
  totalBytes?: number;
  estimatedSeconds?: number | null;
  note?: string | null;
}

export type SetupProgressStatus =
  | "idle"
  | "queued"
  | "scanning"
  | "syncing"
  | "deriving"
  | "refreshing"
  | "embedding"
  | "cancelling"
  | "complete"
  | "failed"
  | "cancelled"
  | "interrupted";

export interface SetupProgress {
  status: SetupProgressStatus;
  phase?: string | null;
  message?: string | null;
  completed?: number | null;
  total?: number | null;
  percent?: number | null;
  estimatedSecondsRemaining?: number | null;
  startedAt?: string | null;
  updatedAt?: string | null;
  error?: string | null;
}

export type SetupStep = "machines" | "history" | "policy" | "build";

export interface SetupPageProps {
  /** Initial values for the local setup form. Omitted values use the safe defaults below. */
  initialConfig?: Partial<SetupConfig>;
  machines?: SetupMachine[];
  estimate?: SetupEstimate | null;
  progress?: SetupProgress | null;
  /** Called whenever a form value changes, so the host can persist a draft. */
  onChange?: (config: SetupConfig) => void;
  /** May return an estimate so a host can remain endpoint-agnostic. */
  onPreview?: (config: SetupConfig) => SetupEstimate | void | Promise<SetupEstimate | void>;
  onStartBuild?: (config: SetupConfig) => void | Promise<void>;
  onCancelBuild?: () => void | Promise<void>;
  onDiscoverMachine?: () => void | Promise<void>;
  onSelectMachine?: (machineId: string) => void;
  onOpenInstructions?: () => void;
  onSelectStep?: (step: SetupStep) => void;
}

export const DEFAULT_SETUP_CONFIG: SetupConfig = {
  historyStart: "",
  historyEnd: "",
  providers: ["codex", "claude", "gemini"],
  includeGitMetadata: true,
  // Exact evidence is retained by default; the two derived search controls are opt-in.
  preserveEncryptedReasoning: true,
  includeReadableReasoningInSearch: false,
  includeReasoningInProjection: false,
};

const PROVIDERS: Array<{ value: SetupProvider; label: string; description: string }> = [
  { value: "codex", label: "Codex", description: "Sessions in ~/.codex" },
  { value: "claude", label: "Claude", description: "Sessions in ~/.claude" },
  { value: "gemini", label: "Gemini", description: "Sessions in ~/.gemini" },
];

const QUICK_RANGES = [
  { label: "All available", value: "all" },
  { label: "Last 30 days", value: "30d" },
  { label: "Last 90 days", value: "90d" },
  { label: "Last year", value: "1y" },
] as const;

const STEP_DETAILS: Array<{ id: SetupStep; number: string; label: string; description: string; icon: typeof Monitor }> = [
  { id: "machines", number: "01", label: "Machines", description: "Find each source computer", icon: Monitor },
  { id: "history", number: "02", label: "History", description: "Choose the time window", icon: CalendarDays },
  { id: "policy", number: "03", label: "Storage & search", description: "Control reasoning retention", icon: ShieldCheck },
  { id: "build", number: "04", label: "Build", description: "Preview and start", icon: Sparkles },
];

export default function SetupPage({
  initialConfig,
  machines = [],
  estimate = null,
  progress = null,
  onChange,
  onPreview,
  onStartBuild,
  onCancelBuild,
  onDiscoverMachine,
  onSelectMachine,
  onOpenInstructions,
  onSelectStep,
}: SetupPageProps) {
  const [config, setConfig] = useState<SetupConfig>(() => ({ ...DEFAULT_SETUP_CONFIG, ...initialConfig }));
  const [activeStep, setActiveStep] = useState<SetupStep>("machines");
  const [previewEstimate, setPreviewEstimate] = useState<SetupEstimate | null>(null);
  const [action, setAction] = useState<"preview" | "start" | "cancel" | "discover" | "instructions" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const displayedEstimate = previewEstimate ?? estimate;
  const isRunning = Boolean(
    progress &&
      ["queued", "scanning", "syncing", "deriving", "refreshing", "embedding", "cancelling"].includes(
        progress.status,
      ),
  );

  function updateConfig(patch: Partial<SetupConfig>) {
    const next = { ...config, ...patch };
    setConfig(next);
    setPreviewEstimate(null);
    onChange?.(next);
  }

  function selectStep(step: SetupStep) {
    setActiveStep(step);
    onSelectStep?.(step);
  }

  async function runAction(
    name: Exclude<typeof action, null>,
    callback: (() => void | Promise<void>) | undefined,
  ) {
    if (!callback) return;
    setAction(name);
    setActionError(null);
    try {
      await callback();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAction(null);
    }
  }

  async function preview() {
    if (!onPreview) return;
    setAction("preview");
    setActionError(null);
    try {
      const nextEstimate = await onPreview(config);
      if (nextEstimate) setPreviewEstimate(nextEstimate);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setAction(null);
    }
  }

  return (
    <div className="setup-page">
      <PageHeader eyebrow="Archive setup" title="Make every machine part of one evidence archive">
        <button className="button" type="button" onClick={() => void runAction("instructions", onOpenInstructions)}>
          <BookOpen size={15} aria-hidden="true" /> Setup guide
        </button>
      </PageHeader>

      <section className="panel setup-hero" aria-labelledby="setup-hero-title">
        <div className="setup-hero-copy">
          <span className="eyebrow">One deliberate build</span>
          <h2 id="setup-hero-title">Decide what enters the archive before it gets indexed.</h2>
          <p>
            Source folders remain read-only. This setup chooses which machines and dates to scan,
            then shows the storage impact before PostgreSQL and the optional vector projection are built.
          </p>
        </div>
        <div className="setup-hero-status" aria-label="Setup summary">
          <Badge tone={isRunning ? "partial" : progress?.status === "complete" ? "success" : "neutral"}>
            {progressLabel(progress)}
          </Badge>
          <strong>{machines.length ? `${machines.length} machine${machines.length === 1 ? "" : "s"} connected` : "No machines connected yet"}</strong>
          <span>{scopeLabel(config)}</span>
        </div>
      </section>

      <nav className="setup-step-cards" aria-label="Archive setup steps">
        {STEP_DETAILS.map(({ id, number, label, description, icon: Icon }) => (
          <button
            className={`setup-step-card ${activeStep === id ? "active" : ""}`}
            type="button"
            key={id}
            aria-current={activeStep === id ? "step" : undefined}
            aria-controls={`setup-section-${id}`}
            onClick={() => selectStep(id)}
          >
            <span className="setup-step-number">{number}</span>
            <Icon size={18} aria-hidden="true" />
            <span className="setup-step-copy"><strong>{label}</strong><small>{description}</small></span>
            <ChevronRight size={15} aria-hidden="true" />
          </button>
        ))}
      </nav>

      {actionError ? <ErrorNotice message={actionError} /> : null}

      <section className="panel setup-section setup-machines" id="setup-section-machines" aria-labelledby="setup-machines-title">
        <SectionHeading step="01" eyebrow="Source computers" title="Connect the machines that own the chats" id="setup-machines-title">
          Machine identity is recorded with each source. The central database can combine machines without copying their source folders.
        </SectionHeading>
        <div className="setup-machine-list" aria-live="polite">
          {machines.map((machine) => (
            <button
              className="setup-machine-card"
              type="button"
              key={machine.id}
              onClick={() => onSelectMachine?.(machine.id)}
              disabled={!onSelectMachine}
            >
              <span className="setup-machine-icon"><Monitor size={18} aria-hidden="true" /></span>
              <span className="setup-machine-copy">
                <strong>{machine.name}</strong>
                <small>{machine.platform ?? "Platform not reported"}{machine.note ? ` · ${machine.note}` : ""}</small>
                <span className="setup-machine-roots">
                  {machine.sourceRoots.length ? machine.sourceRoots.map((root) => root.provider).join(" · ") : "No source roots discovered"}
                </span>
              </span>
              <span className="setup-machine-meta">
                <Badge tone={machineTone(machine.status)}>{machineStatusLabel(machine.status)}</Badge>
                {machine.eventCount != null ? <small>{formatNumber(machine.eventCount)} events</small> : null}
                {machine.lastSeenAt ? <small>Seen {formatDate(machine.lastSeenAt, true)}</small> : null}
              </span>
              {onSelectMachine ? <ChevronRight size={16} aria-hidden="true" /> : null}
            </button>
          ))}
          {machines.length === 0 ? (
            <div className="setup-empty-card">
              <CloudCog size={21} aria-hidden="true" />
              <div><strong>Start with this machine</strong><p>Discover Codex, Claude, Gemini, and optional Git roots without modifying them.</p></div>
            </div>
          ) : null}
        </div>
        <div className="setup-section-actions">
          <button className="button button-primary" type="button" onClick={() => void runAction("discover", onDiscoverMachine)} disabled={action === "discover"}>
            {action === "discover" ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <RefreshCw size={15} aria-hidden="true" />}
            {action === "discover" ? "Discovering…" : machines.length ? "Discover another machine" : "Discover this machine"}
          </button>
          <span className="setup-inline-note"><Info size={14} aria-hidden="true" /> A remote machine needs its own writer configuration and access to this database over Tailscale.</span>
        </div>
      </section>

      <div className="setup-two-column">
        <section className="panel setup-section" id="setup-section-history" aria-labelledby="setup-history-title">
          <SectionHeading step="02" eyebrow="History window" title="Choose how far back to process" id="setup-history-title">
            Start small if you are validating the installation. You can extend the range and rerun the derived indexes later.
          </SectionHeading>
          <div className="setup-quick-ranges" aria-label="History presets">
            {QUICK_RANGES.map((range) => {
              const selected = rangeSelected(range.value, config);
              return <button className={selected ? "active" : ""} type="button" aria-pressed={selected} key={range.value} onClick={() => applyQuickRange(range.value, updateConfig)}>{range.label}</button>;
            })}
          </div>
          <div className="setup-date-grid">
            <label><span>From</span><input type="date" aria-label="History start date" value={config.historyStart} onChange={(event) => updateConfig({ historyStart: event.target.value })} /></label>
            <label><span>Through</span><input type="date" aria-label="History end date" value={config.historyEnd} onChange={(event) => updateConfig({ historyEnd: event.target.value })} /></label>
          </div>
          <p className="setup-field-help"><CalendarDays size={14} aria-hidden="true" /> Empty dates mean all available source history. This filter applies to the build; the vector map can have its own view filter.</p>
          <fieldset className="setup-choice-fieldset">
            <legend>Conversation sources</legend>
            <div className="setup-provider-grid">
              {PROVIDERS.map((provider) => (
                <label className="setup-choice-card" key={provider.value}>
                  <input type="checkbox" checked={config.providers.includes(provider.value)} onChange={(event) => updateProviders(provider.value, event.target.checked, config, updateConfig)} />
                  <span><strong>{provider.label}</strong><small>{provider.description}</small></span>
                </label>
              ))}
              <label className="setup-choice-card">
                <input type="checkbox" checked={config.includeGitMetadata} onChange={(event) => updateConfig({ includeGitMetadata: event.target.checked })} />
                <span><strong>Git metadata</strong><small>Repositories, commits, paths—not file contents</small></span>
              </label>
            </div>
          </fieldset>
        </section>

        <section className="panel setup-section" id="setup-section-policy" aria-labelledby="setup-policy-title">
          <SectionHeading step="03" eyebrow="Storage and retrieval" title="Choose what reasoning is used for" id="setup-policy-title">
            Raw evidence, lexical search, and vector projection are separate decisions. Changing a derived policy never rewrites the original chat archive.
          </SectionHeading>
          <fieldset className="setup-policy-list">
            <legend className="sr-only">Reasoning retention and indexing policy</legend>
            <PolicyChoice
              checked={config.preserveEncryptedReasoning}
              onChange={(checked) => updateConfig({ preserveEncryptedReasoning: checked })}
              icon={<Database size={17} aria-hidden="true" />}
              title="Preserve encrypted raw reasoning"
              description="Keep exact provider payloads for audit and replay. This is usually the largest reasoning category."
              badge="Raw evidence"
            />
            <PolicyChoice
              checked={config.includeReadableReasoningInSearch}
              onChange={(checked) => updateConfig({ includeReadableReasoningInSearch: checked })}
              icon={<HardDrive size={17} aria-hidden="true" />}
              title="Include readable reasoning in text search"
              description="Let full-text search match visible reasoning summaries. It does not add those summaries to the vector projection."
              badge="Lexical"
            />
            <PolicyChoice
              checked={config.includeReasoningInProjection}
              onChange={(checked) => updateConfig({ includeReasoningInProjection: checked })}
              icon={<Sparkles size={17} aria-hidden="true" />}
              title="Include reasoning in the vector projection"
              description="Embed readable reasoning alongside conversation text. It can enlarge the projection and change cluster shape."
              badge="Semantic"
            />
          </fieldset>
          <div className="setup-policy-note"><ShieldCheck size={15} aria-hidden="true" /><span>Encrypted payloads are not readable search text. Excluding them from the projection keeps opaque or repetitive traces out of semantic neighborhoods.</span></div>
        </section>
      </div>

      <section className="panel setup-section setup-build" id="setup-section-build" aria-labelledby="setup-build-title">
        <div className="setup-build-header">
          <SectionHeading step="04" eyebrow="Preview and build" title="See the cost before you commit" id="setup-build-title">
            Preview uses the selected machines, date range, providers, and reasoning policy. Start only after the estimate looks right.
          </SectionHeading>
          <div className="setup-build-actions">
            <button className="button" type="button" onClick={() => void preview()} disabled={!onPreview || action === "preview" || isRunning}>
              {action === "preview" ? <LoaderCircle className="setup-spin" size={15} aria-hidden="true" /> : <HardDrive size={15} aria-hidden="true" />}
              {action === "preview" ? "Calculating…" : "Preview build"}
            </button>
            <button className="button button-primary" type="button" onClick={() => void runAction("start", onStartBuild ? () => onStartBuild(config) : undefined)} disabled={!onStartBuild || isRunning || config.providers.length === 0}>
              <Play size={15} aria-hidden="true" /> {isRunning ? "Build in progress" : "Start archive build"}
            </button>
          </div>
        </div>

        <EstimateSummary estimate={displayedEstimate} reasoningIncluded={config.includeReasoningInProjection} />
        <BuildProgress progress={progress} onCancel={onCancelBuild ? () => void runAction("cancel", onCancelBuild) : undefined} cancelling={action === "cancel"} />
      </section>

      <section className="setup-multi-machine-note" aria-labelledby="setup-multi-title">
        <div className="setup-multi-icon"><Server size={19} aria-hidden="true" /></div>
        <div><span className="eyebrow">Multi-machine guide</span><h2 id="setup-multi-title">One shared database, many read-only source writers.</h2><p>Install the same archive worker on each computer, give it a unique machine name, and point it at this PostgreSQL host. Only the central worker should run migrations and global derived refreshes.</p></div>
        <button className="button" type="button" onClick={() => void runAction("instructions", onOpenInstructions)}><BookOpen size={15} aria-hidden="true" /> Open instructions</button>
      </section>
    </div>
  );
}

function SectionHeading({ step, eyebrow, title, id, children }: { step: string; eyebrow: string; title: string; id: string; children: ReactNode }) {
  return <div className="setup-section-heading"><div className="setup-section-number">{step}</div><div><span className="eyebrow">{eyebrow}</span><h2 id={id}>{title}</h2><p>{children}</p></div></div>;
}

function PolicyChoice({ checked, onChange, icon, title, description, badge }: { checked: boolean; onChange: (checked: boolean) => void; icon: ReactNode; title: string; description: string; badge: string }) {
  return <label className={`setup-policy-choice ${checked ? "selected" : ""}`}><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><span className="setup-policy-icon">{icon}</span><span className="setup-policy-copy"><strong>{title}</strong><small>{description}</small></span><Badge tone={checked ? "success" : "neutral"}>{checked ? <><Check size={11} aria-hidden="true" /> {badge}</> : "Excluded"}</Badge></label>;
}

function EstimateSummary({ estimate, reasoningIncluded }: { estimate: SetupEstimate | null; reasoningIncluded: boolean }) {
  if (!estimate) return <div className="setup-estimate-empty"><HardDrive size={19} aria-hidden="true" /><div><strong>No build estimate yet</strong><p>Choose a scope, then select “Preview build” to calculate records, storage, and semantic window counts.</p></div></div>;
  const total = estimate.totalBytes ?? estimate.rawBytes ?? 0;
  const reasoning = estimate.encryptedReasoningBytes ?? 0;
  const reasoningShare = total > 0 ? Math.round((reasoning / total) * 100) : 0;
  return <div className="setup-estimate" aria-label="Build estimate"><div className="setup-estimate-total"><span>Estimated storage</span><strong>{formatBytes(total)}</strong><small>{estimate.estimatedSeconds != null ? `about ${formatDuration(estimate.estimatedSeconds)}` : "duration will be measured during the build"}</small></div><div className="setup-estimate-metrics"><EstimateMetric label="Sources" value={estimate.sourceCount} /><EstimateMetric label="Sessions" value={estimate.sessionCount} /><EstimateMetric label="Events" value={estimate.eventCount} /><EstimateMetric label="Semantic windows" value={estimate.semanticWindowCount} /><EstimateMetric label="Encrypted reasoning" value={estimate.encryptedReasoningBytes} bytes /><EstimateMetric label="Readable reasoning" value={estimate.readableReasoningBytes} bytes /></div><div className="setup-estimate-breakdown"><div className="setup-estimate-bar" role="img" aria-label={`${reasoningShare}% of estimated storage is encrypted reasoning`}><span style={{ width: `${Math.min(100, reasoningShare)}%` }} /></div><span>{reasoningShare}% encrypted reasoning{reasoningIncluded ? "; semantic reasoning is included" : "; semantic reasoning is excluded"}</span></div>{estimate.note ? <p className="setup-field-help"><Info size={14} aria-hidden="true" /> {estimate.note}</p> : null}</div>;
}

function EstimateMetric({ label, value, suffix = "", bytes = false }: { label: string; value?: number; suffix?: string; bytes?: boolean }) {
  return <div><span>{label}</span><strong>{value == null ? "—" : bytes ? formatBytes(value) : `${formatNumber(value)}${suffix}`}</strong></div>;
}

function BuildProgress({ progress, onCancel, cancelling }: { progress: SetupProgress | null; onCancel?: () => void; cancelling: boolean }) {
  if (!progress || progress.status === "idle") return <div className="setup-progress setup-progress-idle"><span><Info size={15} aria-hidden="true" /> No build is running.</span><small>The archive remains available while a later semantic projection is built.</small></div>;
  const percent = progressPercent(progress);
  const failed = progress.status === "failed" || progress.status === "interrupted";
  const complete = progress.status === "complete";
  const terminal = complete || failed || progress.status === "cancelled";
  return <div className={`setup-progress ${failed ? "failed" : complete ? "complete" : "active"}`} aria-labelledby="setup-progress-title"><div className="setup-progress-header"><div><span className="eyebrow">Build status</span><h3 id="setup-progress-title">{progressLabel(progress)}</h3></div><strong>{Math.round(percent)}%</strong></div><div className="setup-progress-track" role="progressbar" aria-label="Archive build progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{ width: `${percent}%` }} /></div><div className="setup-progress-meta"><span>{progress.message ?? progress.phase ?? (failed ? "The build stopped with an error." : complete ? "The archive and selected projections are current." : "Preparing the next phase…")}</span>{progress.estimatedSecondsRemaining != null && !terminal ? <span>{formatDuration(progress.estimatedSecondsRemaining)} remaining</span> : null}{onCancel && !terminal ? <button className="text-button" type="button" onClick={onCancel} disabled={cancelling}>{cancelling ? "Stopping…" : "Stop build"}</button> : null}</div>{failed && progress.error ? <p className="setup-progress-error"><TriangleAlert size={14} aria-hidden="true" /> {progress.error}</p> : null}{progress.startedAt ? <small className="setup-progress-time">Started {formatDate(progress.startedAt, true)}</small> : null}</div>;
}

function progressPercent(progress: SetupProgress): number {
  if (progress.percent != null) return clamp(progress.percent, 0, 100);
  if (progress.completed != null && progress.total) return clamp((progress.completed / progress.total) * 100, 0, 100);
  return progress.status === "complete" ? 100 : 0;
}

function progressLabel(progress: SetupProgress | null): string {
  if (!progress || progress.status === "idle") return "Ready to configure";
  if (progress.status === "complete") return "Archive current";
  if (progress.status === "failed" || progress.status === "interrupted") return "Build needs attention";
  if (progress.status === "cancelled") return "Build cancelled";
  if (progress.status === "queued") return "Queued";
  return progress.phase || progress.status.charAt(0).toUpperCase() + progress.status.slice(1);
}

function machineStatusLabel(status: SetupMachineStatus): string {
  return status === "needs-setup" ? "Needs setup" : status.charAt(0).toUpperCase() + status.slice(1);
}

function machineTone(status: SetupMachineStatus): string {
  if (status === "current" || status === "connected") return "success";
  if (status === "syncing") return "partial";
  if (status === "offline") return "danger";
  return "neutral";
}

function scopeLabel(config: SetupConfig): string {
  const start = config.historyStart || "oldest";
  const end = config.historyEnd || "newest";
  return `${start} → ${end}`;
}

function rangeSelected(value: (typeof QUICK_RANGES)[number]["value"], config: SetupConfig): boolean {
  if (value === "all") return !config.historyStart && !config.historyEnd;
  if (!config.historyEnd || config.historyEnd !== todayInputValue()) return false;
  const expectedStart = new Date();
  if (value === "30d") expectedStart.setDate(expectedStart.getDate() - 30);
  if (value === "90d") expectedStart.setDate(expectedStart.getDate() - 90);
  if (value === "1y") expectedStart.setFullYear(expectedStart.getFullYear() - 1);
  return config.historyStart === toInputDate(expectedStart);
}

function applyQuickRange(value: (typeof QUICK_RANGES)[number]["value"], update: (patch: Partial<SetupConfig>) => void) {
  if (value === "all") {
    update({ historyStart: "", historyEnd: "" });
    return;
  }
  const start = new Date();
  if (value === "30d") start.setDate(start.getDate() - 30);
  if (value === "90d") start.setDate(start.getDate() - 90);
  if (value === "1y") start.setFullYear(start.getFullYear() - 1);
  update({ historyStart: toInputDate(start), historyEnd: todayInputValue() });
}

function updateProviders(provider: SetupProvider, included: boolean, config: SetupConfig, update: (patch: Partial<SetupConfig>) => void) {
  const providers = included ? [...new Set([...config.providers, provider])] : config.providers.filter((item) => item !== provider);
  update({ providers });
}

function todayInputValue(): string {
  return toInputDate(new Date());
}

function toInputDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
